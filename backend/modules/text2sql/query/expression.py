from uuid import UUID

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from ..common.errors import Text2SqlMetricNotRunnable

DIALECT = "postgres"
MAX_EXPRESSION_LENGTH = 2000
MAX_NODES = 200

ALLOWED_NODES: tuple[type[exp.Expression], ...] = (
    exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean, exp.Paren, exp.Neg,
    exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Distinct, exp.Star,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.And, exp.Or, exp.Not, exp.Is, exp.In, exp.Between,
    exp.Like, exp.ILike, exp.Case, exp.If, exp.Coalesce, exp.Nullif, exp.Round, exp.Abs, exp.Ceil, exp.Floor,
    exp.Greatest, exp.Least, exp.Cast, exp.DataType,
)
ALLOWED_CAST_TYPES = frozenset({
    exp.DataType.Type.INT, exp.DataType.Type.BIGINT, exp.DataType.Type.SMALLINT, exp.DataType.Type.DECIMAL,
    exp.DataType.Type.DOUBLE, exp.DataType.Type.FLOAT, exp.DataType.Type.VARCHAR, exp.DataType.Type.TEXT,
    exp.DataType.Type.DATE, exp.DataType.Type.TIMESTAMP, exp.DataType.Type.TIMESTAMPTZ,
    exp.DataType.Type.BOOLEAN,
})


def _reject(reason: str) -> Text2SqlMetricNotRunnable:
    return Text2SqlMetricNotRunnable(f"Biểu thức metric không an toàn hoặc không hỗ trợ: {reason}")


def compile_metric_expression(expression: str, columns_by_name: dict[str, tuple[UUID, str]]) -> str:
    if len(expression) > MAX_EXPRESSION_LENGTH or ";" in expression:
        raise _reject("quá dài hoặc có nhiều câu lệnh.")
    try:
        statements = parse(expression, read=DIALECT)
    except SqlglotError:
        raise _reject("không đọc được cú pháp.") from None
    except RecursionError:
        raise _reject("lồng ngoặc hoặc hàm quá sâu.") from None
    if len(statements) != 1 or statements[0] is None:
        raise _reject("phải là đúng một biểu thức.")
    tree = statements[0]
    nodes = list(tree.walk())
    if len(nodes) > MAX_NODES:
        raise _reject("quá phức tạp.")
    for node in nodes:
        if not isinstance(node, ALLOWED_NODES):
            raise _reject(f"không cho phép {type(node).__name__}.")
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise _reject("dấu * chỉ dùng trong COUNT(*).")
        if isinstance(node, exp.DataType) and node.this not in ALLOWED_CAST_TYPES:
            raise _reject("kiểu dữ liệu ép kiểu không được hỗ trợ.")
        if isinstance(node, exp.Column) and (node.table or node.args.get("db")):
            raise _reject("không dùng tên cột kèm bảng hoặc schema.")
    if not any(isinstance(node, exp.AggFunc) for node in nodes):
        raise _reject("phải chứa hàm tổng hợp như SUM, COUNT, AVG.")
    for column in list(tree.find_all(exp.Column)):
        known = columns_by_name.get(column.name.lower())
        if known is None:
            raise _reject(f"cột '{column.name}' không thuộc bảng của metric.")
        column.replace(exp.column(known[1], quoted=True))
    return tree.sql(dialect=DIALECT)
