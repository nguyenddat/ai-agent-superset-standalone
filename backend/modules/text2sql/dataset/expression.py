from collections.abc import Callable

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from ..common.errors import Text2SqlInvalidRequest
from ..query.expression import ALLOWED_CAST_TYPES, ALLOWED_NODES, DIALECT, MAX_EXPRESSION_LENGTH, MAX_NODES

Resolver = Callable[[str, str], exp.Column]


def reject(reason: str) -> Text2SqlInvalidRequest:
    return Text2SqlInvalidRequest(f"Biểu thức không an toàn hoặc không hỗ trợ: {reason}")


def aggregate_nodes(tree: exp.Expression) -> list[exp.AggFunc]:
    return [node for node in tree.walk() if isinstance(node, exp.AggFunc)]


def _check_aggregate(node: exp.AggFunc) -> None:
    extra = [key for key, value in node.args.items() if key not in ("this", "big_int") and value]
    if extra or node.this is None:
        raise reject("hàm tổng hợp chỉ nhận một đối số.")
    if any(isinstance(inner, exp.AggFunc) for inner in node.this.walk()):
        raise reject("không lồng hàm tổng hợp trong hàm tổng hợp khác.")


def _check_node(node: exp.Expression) -> None:
    if not isinstance(node, ALLOWED_NODES):
        raise reject(f"không cho phép {type(node).__name__}.")
    if isinstance(node, exp.Star) and not (isinstance(node.parent, exp.Count) and node.arg_key == "this"):
        raise reject("dấu * chỉ dùng trong COUNT(*).")
    if isinstance(node, exp.DataType) and node.this not in ALLOWED_CAST_TYPES:
        raise reject("kiểu dữ liệu ép kiểu không được hỗ trợ.")
    if isinstance(node, exp.Distinct):
        if not isinstance(node.parent, exp.AggFunc) or node.arg_key != "this" or len(node.expressions) != 1:
            raise reject("DISTINCT chỉ dùng với một cột bên trong hàm tổng hợp, ví dụ COUNT(DISTINCT bang.cot).")
    if isinstance(node, exp.Column):
        if not isinstance(node.this, exp.Identifier):
            raise reject("cột phải viết dạng bang.cot.")
        if node.args.get("db") or node.args.get("catalog"):
            raise reject("không ghi schema; viết cột dạng bang.cot.")
        if not node.table:
            raise reject(f"cột '{node.name}' phải ghi kèm tên bảng, dạng bang.cot.")
    if isinstance(node, exp.AggFunc):
        _check_aggregate(node)


def parse_dataset_expression(text: str, resolve: Resolver) -> exp.Expression:
    if not text.strip() or len(text) > MAX_EXPRESSION_LENGTH:
        raise reject("rỗng hoặc quá dài.")
    try:
        statements = parse(text, read=DIALECT)
    except SqlglotError:
        raise reject("không đọc được cú pháp.") from None
    except RecursionError:
        raise reject("lồng ngoặc hoặc hàm quá sâu.") from None
    if len(statements) != 1 or statements[0] is None:
        raise reject("phải là đúng một biểu thức.")
    tree = statements[0]
    nodes = list(tree.walk())
    if len(nodes) > MAX_NODES:
        raise reject("quá phức tạp.")
    for node in nodes:
        _check_node(node)
    for column in list(tree.find_all(exp.Column)):
        resolved = resolve(column.table, column.name)
        if column is tree:
            tree = resolved
        else:
            column.replace(resolved)
    return tree
