import math
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..common.errors import Text2SqlConnectionNotFound, Text2SqlInvalidRequest, Text2SqlQueryFailed
from ..vector_store.ingestion.documents.context import load_context
from .compiler import CompiledQuery, compile_query
from .executor import RawResult, run_read_only
from .pii import MaskColumn, PiiMasker
from .schemas import PiiReport, QueryMetricInfo, QueryPlan, QueryResult

PII_NOTICE = (
    "Kết quả có thể chứa dữ liệu cá nhân. Các giá trị nhận diện được (cột đánh dấu PII, số điện thoại, email, "
    "CCCD/CMND, thẻ, IP...) đã được thay bằng placeholder nhất quán trong phản hồi này; cùng một giá trị luôn "
    "có cùng placeholder. Không cố khôi phục giá trị gốc."
)

Runner = Callable[..., RawResult]
NUMERIC_VALUE_TYPES = frozenset({"integer", "decimal", "float"})


def value_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, float):
        return "float"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, str):
        return "text"
    return None


def value_types(rows: list[tuple[Any, ...]], width: int) -> list[str | None]:
    kinds: list[str | None] = []
    for index in range(width):
        found = {value_type(row[index]) for row in rows if index < len(row) and row[index] is not None}
        found.discard(None)
        if len(found) == 1:
            kinds.append(found.pop())
        elif found and found <= NUMERIC_VALUE_TYPES:
            kinds.append("decimal" if "decimal" in found else "float")
        else:
            kinds.append(None)
    return kinds


def format_cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "<binary>"
    return str(value)


class QueryService:
    def __init__(self, session: Session, runner: Runner = run_read_only, masker: PiiMasker | None = None) -> None:
        self.session = session
        self.runner = runner
        self.masker = masker or PiiMasker()

    def prepare(self, connection_id: UUID, plan: QueryPlan) -> CompiledQuery:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        context = load_context(self.session, connection_id)
        return compile_query(context, connection_id, plan, config.text2sql_query_max_rows)

    def execute(self, compiled: CompiledQuery, source_url: URL, confirmation: str = "not_required") -> QueryResult:
        raw = self.runner(
            source_url, compiled.sql, compiled.parameters, compiled.expanding,
            compiled.limit + 1, config.text2sql_query_timeout_seconds,
        )
        truncated = len(raw.rows) > compiled.limit
        kept = raw.rows[:compiled.limit]
        rows = [[format_cell(value) for value in row] for row in kept]
        masked_rows, report = self.masker.mask(
            [MaskColumn(
                label=column.spec.name, name=column.name, scan=column.scan, flagged=column.spec.contains_pii,
            ) for column in compiled.columns],
            rows,
        )
        pii = PiiReport(
            confirmation=confirmation, masked_columns=report.masked_columns, detected=report.detected,
            warning=PII_NOTICE if report.detected or report.masked_columns else None,
        )
        return QueryResult(
            metric=QueryMetricInfo(
                metric_id=compiled.metric_id, name=compiled.metric_name, label=compiled.metric_label,
                format=compiled.metric_format, currency=compiled.metric_currency,
                warning_text=compiled.metric_warning, table=compiled.table_label,
            ),
            columns=[column.spec for column in compiled.columns], rows=masked_rows, row_count=len(masked_rows),
            truncated=truncated, limit=compiled.limit, sql=compiled.sql, parameters=_printable(compiled.parameters),
            pii=pii, elapsed_ms=raw.elapsed_ms, value_types=value_types(kept, len(compiled.columns)),
        )

    def resolve_source(self, connection_id: UUID) -> URL:
        connection = self.session.get(DatabaseConnection, connection_id)
        if connection is None:
            raise Text2SqlConnectionNotFound()
        if not connection.is_active:
            raise Text2SqlInvalidRequest("Connection đang tạm dừng nên chưa thể truy vấn.")
        try:
            uri = Fernet(config.require_connection_encryption_key().encode()).decrypt(
                connection.uri_ciphertext.encode()
            ).decode("utf-8")
            return make_url(uri)
        except (InvalidToken, UnicodeError, ValueError, RuntimeError):
            raise Text2SqlQueryFailed() from None


def _printable(parameters: dict[str, Any]) -> dict[str, Any]:
    return {name: _printable_value(value) for name, value in parameters.items()}


def _printable_value(value: Any) -> Any:
    if isinstance(value, list):
        return [format_cell(item) for item in value]
    return format_cell(value)
