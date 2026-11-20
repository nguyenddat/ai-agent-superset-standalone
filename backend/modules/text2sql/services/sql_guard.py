from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from backend.agent_package.tool_agent import ToolError

DIALECT = "postgres"
MAX_SQL_LENGTH = 20000
BLOCKED_PREFIXES = ("pg_", "dblink", "lo_", "txid_", "crosstab")
BLOCKED_SUBSTRINGS = ("to_xml",)
BLOCKED_FUNCTIONS = frozenset({
    "set_config", "current_setting", "nextval", "setval", "currval", "copy", "ts_stat", "ts_rewrite", "connectby",
})
TABLE_FUNCTIONS = (exp.GenerateSeries, exp.ExplodingGenerateSeries, exp.Unnest)
WRITES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.Into,
    exp.Lock, exp.TruncateTable, exp.Copy,
)


def _function_name(node: exp.Func) -> str:
    return (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def _blocked_function(name: str) -> bool:
    return (
        name.startswith(BLOCKED_PREFIXES) or name in BLOCKED_FUNCTIONS
        or any(part in name for part in BLOCKED_SUBSTRINGS)
    )


def _cte_in_scope(table: exp.Table, name: str) -> bool:
    child, node = table, table.parent
    while node is not None:
        if isinstance(node, exp.With):
            ctes = node.expressions
            position = next((index for index, cte in enumerate(ctes) if cte is child), len(ctes))
            visible = ctes if node.args.get("recursive") else ctes[:position]
            if any(cte.alias_or_name.lower() == name for cte in visible):
                return True
        elif isinstance(node, exp.Query) and child is not node.args.get("with_"):
            with_ = node.args.get("with_")
            if with_ and any(cte.alias_or_name.lower() == name for cte in with_.expressions):
                return True
        child, node = node, node.parent
    return False


def validate_select(sql: str, table_names: dict[str, str]) -> str:
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise ToolError("SQL rỗng.")
    if len(text) > MAX_SQL_LENGTH:
        raise ToolError(f"SQL dài quá {MAX_SQL_LENGTH} ký tự.")
    try:
        statements = [item for item in parse(text, read=DIALECT) if item is not None]
    except SqlglotError as error:
        raise ToolError(f"Không đọc được cú pháp SQL (PostgreSQL): {str(error).splitlines()[0]}") from None
    except RecursionError:
        raise ToolError("SQL lồng quá sâu.") from None
    if len(statements) != 1:
        raise ToolError("Chỉ gửi đúng một câu lệnh SELECT.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise ToolError("Chỉ được chạy câu lệnh SELECT (có thể kèm WITH, UNION).")
    for node in tree.walk():
        if isinstance(node, WRITES):
            raise ToolError(f"Không được dùng {type(node).__name__.upper()}; chỉ được đọc dữ liệu.")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if _blocked_function(name):
                raise ToolError(f"Không được gọi hàm hệ thống {name}.")
    for table in list(tree.find_all(exp.Table)):
        if not isinstance(table.this, exp.Identifier):
            if not isinstance(table.this, TABLE_FUNCTIONS):
                raise ToolError("Trong FROM chỉ được dùng bảng của connection, CTE, generate_series hoặc unnest.")
            continue
        if table.args.get("catalog"):
            raise ToolError(f"Không dùng tên database trong '{table.sql(dialect=DIALECT)}'.")
        name = table.name.lower()
        if not table.db and _cte_in_scope(table, name):
            continue
        key = f"{table.db.lower()}.{name}" if table.db else name
        qualified = table_names.get(key)
        if qualified is None:
            hint = "Ghi đủ schema.bảng." if not table.db else "Dùng get_table để xem bảng có sẵn."
            raise ToolError(f"Bảng '{table.sql(dialect=DIALECT)}' không có trong connection này. {hint}")
        schema, _, table_name = qualified.partition(".")
        table.set("db", exp.to_identifier(schema, quoted=True))
        table.set("this", exp.to_identifier(table_name, quoted=True))
    return tree.sql(dialect=DIALECT)
