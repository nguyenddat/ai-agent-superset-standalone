import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.modules.database_connection.models import DatabaseColumn

from ..models import ColumnDictionary, TableColumnRole, TableDictionary
from ..utils.exceptions import (
    DataDictionaryValidationError,
    DictionaryAutofillFailedError,
    DictionaryAutofillInProgressError,
    DictionaryAutofillUnavailableError,
)
from . import semantics
from .dictionary_service import DataDictionaryService
from .dictionary_suggester import (
    ColumnSuggestion,
    ColumnSuggestions,
    DictionarySuggester,
    LlmDictionarySuggester,
    TableSuggestion,
)

COLUMN_BATCH_SIZE = 8
MAX_AUTOFILL_COLUMNS = 300

_running: set[UUID] = set()
_running_lock = threading.Lock()


@dataclass(frozen=True)
class AutofillPlan:
    table_id: UUID
    table_context: dict[str, Any]
    column_contexts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def batches(self) -> list[dict[str, Any]]:
        return [
            {**self.table_context, "columns": self.column_contexts[start:start + COLUMN_BATCH_SIZE]}
            for start in range(0, len(self.column_contexts), COLUMN_BATCH_SIZE)
        ]


@dataclass(frozen=True)
class AutofillEvent:
    name: str
    data: dict[str, Any]


def _clip(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return value.strip()[:max_length] or None


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _checked_provider_error(error: Exception) -> None:
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        raise DictionaryAutofillUnavailableError("Nhà cung cấp mô hình từ chối API key.") from error
    if status == 402:
        raise DictionaryAutofillUnavailableError("API key của nhà cung cấp mô hình đã hết hạn mức.") from error


class DataDictionaryAutofillService:
    def __init__(self, session: Session, suggester: DictionarySuggester | None = None) -> None:
        self.session = session
        self.dictionary = DataDictionaryService(session)
        self.suggester = suggester or LlmDictionarySuggester()

    def prepare(self, table_id: UUID) -> AutofillPlan:
        current = self.dictionary.get_table_dictionary(table_id)
        columns = current["columns"]
        if not columns:
            raise DataDictionaryValidationError("Bảng chưa có cột nào để mô tả; hãy đồng bộ metadata trước.")
        if len(columns) > MAX_AUTOFILL_COLUMNS:
            raise DataDictionaryValidationError(f"Tự động điền hỗ trợ tối đa {MAX_AUTOFILL_COLUMNS} cột mỗi bảng.")
        try:
            self.suggester.ensure_ready()
        except RuntimeError as error:
            raise DictionaryAutofillUnavailableError() from error
        with _running_lock:
            if table_id in _running:
                raise DictionaryAutofillInProgressError()
            _running.add(table_id)

        plan = AutofillPlan(
            table_id=table_id,
            table_context={
                "schema_name": current["schema_name"],
                "table_name": current["table_name"],
                "table_type": current["table_type"],
                "table_description": current["description"],
            },
            column_contexts=[
                {
                    "column_name": column["name"],
                    "data_type": column["data_type"],
                    "is_nullable": column["is_nullable"],
                    "is_primary_key": column["source_is_primary_key"],
                    "description": column["description"],
                }
                for column in columns
            ],
        )
        # The read transaction ends here so no connection sits idle in a transaction while the model answers.
        self.session.rollback()
        return plan

    @staticmethod
    def release(plan: AutofillPlan) -> None:
        with _running_lock:
            _running.discard(plan.table_id)

    def events(self, plan: AutofillPlan) -> Iterator[AutofillEvent]:
        total = len(plan.column_contexts)
        batches = plan.batches
        yield AutofillEvent("status", {"processed": 0, "total": total, "message": "Đang chuẩn bị gợi ý"})

        suggestions: dict[str, ColumnSuggestion] = {}
        processed = failed = 0
        for index, result in self.suggester.suggest_column_batches(batches):
            names = [column["column_name"] for column in batches[index]["columns"]]
            processed += len(names)
            if isinstance(result, Exception):
                _checked_provider_error(result)
                failed += len(names)
                continue
            accepted = self._accepted(result, names)
            failed += len(names) - len(accepted)
            suggestions.update(accepted)
            self._fill_columns(plan.table_id, accepted)
            yield AutofillEvent("columns", {
                "columns": self._describe_columns(plan.table_id, set(accepted)),
                "processed": processed,
                "total": total,
            })

        yield AutofillEvent("status", {"processed": processed, "total": total, "message": "Đang gợi ý mô tả bảng"})
        table_suggestion = self._suggest_table(plan, suggestions)
        if not suggestions and table_suggestion is None:
            raise DictionaryAutofillFailedError()
        if table_suggestion is not None:
            self._fill_table(plan.table_id, table_suggestion)
        yield AutofillEvent("table", self.dictionary.get_table_dictionary(plan.table_id))
        yield AutofillEvent("done", {
            "processed": processed,
            "total": total,
            "failed_columns": failed,
            "table_filled": table_suggestion is not None,
        })

    @staticmethod
    def _accepted(result: ColumnSuggestions | None, names: list[str]) -> dict[str, ColumnSuggestion]:
        accepted: dict[str, ColumnSuggestion] = {}
        for suggestion in result.suggestions if result else []:
            if suggestion.column_name in names and _clip(suggestion.display_name, 255):
                accepted.setdefault(suggestion.column_name, suggestion)
        return accepted

    def _describe_columns(self, table_id: UUID, names: set[str]) -> list[dict[str, Any]]:
        if not names:
            return []
        columns = self.dictionary.get_table_dictionary(table_id)["columns"]
        return [column for column in columns if column["name"] in names]

    def _suggest_table(
        self, plan: AutofillPlan, column_suggestions: dict[str, ColumnSuggestion],
    ) -> TableSuggestion | None:
        columns = []
        for column in plan.column_contexts:
            suggestion = column_suggestions.get(column["column_name"])
            columns.append({
                **column,
                "display_name": suggestion.display_name if suggestion else None,
                "description": (suggestion.description if suggestion else None) or column["description"],
            })
        try:
            suggestion = self.suggester.suggest_table({**plan.table_context, "columns": columns})
        except Exception as error:
            _checked_provider_error(error)
            return None
        if suggestion is None or not _clip(suggestion.display_name, 255):
            return None
        return suggestion

    def _fill_columns(self, table_id: UUID, suggestions: dict[str, ColumnSuggestion]) -> None:
        if not suggestions:
            return
        table_columns = self.dictionary.columns.read_by_table_id(table_id)
        columns = [column for column in table_columns if column.name in suggestions]
        stored = {
            entry.column_id: entry
            for entry in self.dictionary.column_dictionaries.read_by_column_ids(column.id for column in columns)
        }
        for column in columns:
            entry = stored.get(column.id)
            values = self._column_values(column, entry, suggestions[column.name])
            if entry is None:
                self.dictionary.column_dictionaries.create(ColumnDictionary(column_id=column.id, **values))
            elif values:
                self.dictionary.column_dictionaries.update(entry, values)

    @staticmethod
    def _column_values(
        column: DatabaseColumn, entry: ColumnDictionary | None, suggestion: ColumnSuggestion,
    ) -> dict[str, Any]:
        display_name = _clip(suggestion.display_name, 255)
        description = _clip(suggestion.description, semantics.MAX_DESCRIPTION_LENGTH)
        business_term = _clip(suggestion.business_term, semantics.MAX_DESCRIPTION_LENGTH)
        unit = _clip(suggestion.unit, 128)
        if entry is None:
            return {
                "display_name": display_name or column.name,
                "description": column.description or description,
                "business_term": business_term,
                "unit": unit,
                "temporal_kind": semantics.default_temporal_kind(column.data_type),
            }
        values: dict[str, Any] = {}
        if display_name and entry.display_name.strip() in ("", column.name):
            values["display_name"] = display_name
        if description and _is_blank(entry.description):
            values["description"] = description
        if business_term and _is_blank(entry.business_term):
            values["business_term"] = business_term
        if unit and _is_blank(entry.unit):
            values["unit"] = unit
        return values

    def _fill_table(self, table_id: UUID, suggestion: TableSuggestion) -> None:
        table = self.dictionary.tables.read_by_id(table_id)
        display_name = _clip(suggestion.display_name, 255)
        description = _clip(suggestion.description, semantics.MAX_DESCRIPTION_LENGTH)
        grain_description = _clip(suggestion.grain_description, semantics.MAX_DESCRIPTION_LENGTH)

        dictionary = self.dictionary.table_dictionaries.read_by_table_id(table.id)
        if dictionary is None:
            dictionary = self.dictionary.table_dictionaries.create(TableDictionary(
                table_id=table.id,
                display_name=display_name or table.name,
                description=table.description or description,
                grain_description=grain_description,
            ))
        else:
            values: dict[str, Any] = {}
            if display_name and dictionary.display_name.strip() in ("", table.name):
                values["display_name"] = display_name
            if description and _is_blank(dictionary.description):
                values["description"] = description
            if grain_description and _is_blank(dictionary.grain_description):
                values["grain_description"] = grain_description
            if values:
                self.dictionary.table_dictionaries.update(dictionary, values)
        self._fill_created_at(dictionary, table_id, suggestion.created_at_column)

    def _fill_created_at(self, dictionary: TableDictionary, table_id: UUID, column_name: str | None) -> None:
        if not column_name:
            return
        roles = self.dictionary.column_roles.read_by_parent_ids([dictionary.id])
        if any(role.role == "created_at" for role in roles):
            return
        column = next(
            (column for column in self.dictionary.columns.read_by_table_id(table_id) if column.name == column_name),
            None,
        )
        if column is None or semantics.default_temporal_kind(column.data_type) is None:
            return
        self.dictionary.column_roles.create(
            TableColumnRole(table_dictionary_id=dictionary.id, role="created_at", column_id=column.id)
        )
