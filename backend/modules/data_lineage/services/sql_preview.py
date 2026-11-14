from typing import Any
from uuid import UUID

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from backend.modules.database_connection.models import DatabaseColumn, DatabaseTable

from ..utils.exceptions import LineageValidationError


def preview_sql(
    sql_text: str,
    target_table_id: UUID,
    tables: dict[UUID, tuple[str, DatabaseTable]],
    columns: dict[UUID, list[DatabaseColumn]],
) -> dict[str, Any]:
    try:
        statements = [statement for statement in parse(sql_text, read="postgres") if statement is not None]
    except SqlglotError:
        raise LineageValidationError("Không phân tích được cú pháp SQL PostgreSQL.") from None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise LineageValidationError("Xem trước chỉ nhận một câu SELECT.")
    statement = statements[0]
    if statement.args.get("with_") or any(statement.find_all(exp.Subquery, exp.Union)):
        return {
            "target_table_id": target_table_id, "source_table_ids": [], "dependencies": [],
            "warnings": ["CTE, subquery hoặc UNION cần khai báo nguồn và cột thủ công."],
            "complete": False,
        }
    warnings: list[str] = []
    aliases: dict[str, UUID] = {}
    input_ids: list[UUID] = []
    sources = [statement.args.get("from_")]
    sources.extend(statement.args.get("joins") or [])
    for source in sources:
        table_expression = source.this if source is not None else None
        if not isinstance(table_expression, exp.Table):
            warnings.append("Nguồn không phải bảng trực tiếp; cần khai báo thủ công.")
            continue
        matches = [
            table_id for table_id, (schema_name, table) in tables.items()
            if table.name == table_expression.name and (not table_expression.db or schema_name == table_expression.db)
        ]
        if len(matches) != 1:
            warnings.append(f"Không xác định duy nhất bảng nguồn {table_expression.sql()}.")
            continue
        table_id = matches[0]
        aliases[table_expression.alias_or_name] = table_id
        if table_id not in input_ids:
            input_ids.append(table_id)
    target_columns = {column.name: column.id for column in columns.get(target_table_id, [])}
    source_columns: dict[UUID, dict[str, UUID]] = {
        table_id: {column.name: column.id for column in columns.get(table_id, [])} for table_id in input_ids
    }
    dependencies: list[dict[str, Any]] = []
    seen: set[tuple[UUID, UUID | None, str]] = set()

    def add_columns(expression: exp.Expression, role: str, target_id: UUID | None = None) -> None:
        for column in expression.find_all(exp.Column):
            if column.is_star:
                warnings.append("SELECT * cần xác nhận ánh xạ cột thủ công.")
                continue
            if column.table:
                candidate_tables = [aliases[column.table]] if column.table in aliases else []
            else:
                candidate_tables = [
                    table_id for table_id, known in source_columns.items() if column.name in known
                ]
            matches = [
                source_columns[table_id][column.name]
                for table_id in candidate_tables if column.name in source_columns[table_id]
            ]
            if len(matches) != 1:
                warnings.append(f"Không xác định duy nhất cột nguồn {column.sql()}.")
                continue
            key = (matches[0], target_id, role)
            if key not in seen:
                seen.add(key)
                dependencies.append({
                    "source_column_id": matches[0], "target_column_id": target_id, "role": role,
                })

    for projection in statement.expressions:
        if isinstance(projection, exp.Star):
            warnings.append("SELECT * cần xác nhận ánh xạ cột thủ công.")
            continue
        if any(projection.find_all(exp.Star)):
            warnings.append("Biểu thức dùng * cần xác nhận nguồn dữ liệu thủ công.")
        target_id = target_columns.get(projection.alias_or_name)
        if target_id is None:
            warnings.append(f"Không tìm thấy cột đích cho {projection.sql()}.")
            continue
        add_columns(projection, "value", target_id)
    for join in statement.args.get("joins") or []:
        if join.args.get("on"):
            add_columns(join.args["on"], "join")
        if join.args.get("using"):
            warnings.append("JOIN USING cần xác nhận cột join thủ công.")
    for key, role in (("group", "group"), ("where", "filter"), ("having", "filter")):
        if statement.args.get(key):
            add_columns(statement.args[key], role)
    if any(statement.find_all(exp.Window)):
        warnings.append("Hàm cửa sổ cần kiểm tra lại các cột phụ thuộc.")
    return {
        "target_table_id": target_table_id,
        "source_table_ids": input_ids,
        "dependencies": dependencies,
        "warnings": list(dict.fromkeys(warnings)),
        "complete": not warnings,
    }
