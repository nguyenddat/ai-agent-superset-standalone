from uuid import UUID

from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..common.errors import Text2SqlConnectionNotFound
from ..query.executor import run_read_only
from ..query.pii import MaskColumn, PiiMasker
from ..query.schemas import PiiReport
from ..query.service import PII_NOTICE, QueryService, Runner, _printable, format_cell, value_types
from ..vector_store.ingestion.documents.context import load_context
from .compiler import DatasetCompiledQuery, compile_dataset_query
from .join_schemas import JoinOption
from .schemas import DatasetQueryPlan, DatasetResult


class DatasetQueryService:
    def __init__(self, session: Session, runner: Runner = run_read_only, masker: PiiMasker | None = None) -> None:
        self.session = session
        self.runner = runner
        self.masker = masker or PiiMasker()

    def prepare(self, connection_id: UUID, join: JoinOption, plan: DatasetQueryPlan) -> DatasetCompiledQuery:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        context = load_context(self.session, connection_id)
        return compile_dataset_query(context, connection_id, join, plan, config.text2sql_query_max_rows)

    def execute(
        self, compiled: DatasetCompiledQuery, source_url: URL, confirmation: str = "not_required",
    ) -> DatasetResult:
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
        return DatasetResult(
            columns=[column.spec for column in compiled.columns], rows=masked_rows, row_count=len(masked_rows),
            truncated=truncated, limit=compiled.limit, sql=compiled.sql, parameters=_printable(compiled.parameters),
            pii=pii, elapsed_ms=raw.elapsed_ms, warnings=compiled.warnings,
            value_types=value_types(kept, len(compiled.columns)),
        )

    def resolve_source(self, connection_id: UUID) -> URL:
        return QueryService(self.session, self.runner, self.masker).resolve_source(connection_id)
