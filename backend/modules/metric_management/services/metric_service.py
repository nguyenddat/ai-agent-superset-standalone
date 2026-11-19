from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.common.base_model import utc_now
from backend.modules.business_model.services import DomainAssignment
from backend.modules.database_connection.models import DatabaseConnection, DatabaseTable

from ..models import Metric, SupersetDatabase, SupersetUser, metric_domains
from ..repositories import MetricRepository
from ..utils.exceptions import (
    InvalidMetricError,
    MetricAlreadyExistsError,
    MetricNotFoundError,
    MetricReadOnlyError,
    SupersetDatabaseNotFoundError,
)
from .superset_client import SupersetSnapshot


class MetricService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = MetricRepository(session)
        self.domains = DomainAssignment(session, metric_domains, "metric_id")

    def list_metrics(self, connection_id: UUID | None = None) -> list[dict[str, Any]]:
        rows = self.repository.list(connection_id)
        domains = self.domains.read([row.id for row in rows])
        return [self._metric(row, domains.get(row.id, [])) for row in rows]

    def get_metric(self, metric_id: UUID) -> dict[str, Any]:
        row = self.repository.get(metric_id)
        if row is None:
            raise MetricNotFoundError()
        return self._metric(row, self.domains.read_one(row.id))

    def create_metric(self, values: dict[str, Any]) -> dict[str, Any]:
        table_id = values["table_id"]
        self._require_table(table_id)
        name = values["name"].strip()
        expression = values["expression"].strip()
        self._validate(name, expression)
        if self.repository.find_manual(table_id, name):
            raise MetricAlreadyExistsError()
        domain_ids = self._domain_ids(values.get("business_domain_ids") or [])
        row = Metric(
            origin="manual", table_id=table_id, name=name, expression=expression
        )
        self._apply_editable(row, values)
        self.session.add(row)
        self.session.flush()
        self.domains.replace(row.id, domain_ids)
        return self._metric(row, self.domains.read_one(row.id))

    def update_metric(self, metric_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        row = self.repository.get(metric_id)
        if row is None:
            raise MetricNotFoundError()
        domain_ids = values.get("business_domain_ids")
        if domain_ids is not None:
            domain_ids = self._domain_ids(domain_ids)
        # Domains are local classification, so they stay editable on metrics synced from Superset.
        if row.origin != "manual":
            if set(values) - {"business_domain_ids"}:
                raise MetricReadOnlyError()
            self._replace_domains(row, domain_ids)
            self.session.flush()
            return self._metric(row, self.domains.read_one(row.id))
        table_id = values.get("table_id", row.table_id)
        self._require_table(table_id)
        name_value = values.get("name", row.name)
        expression_value = values.get("expression", row.expression)
        if not isinstance(name_value, str) or not isinstance(expression_value, str):
            raise InvalidMetricError()
        name = name_value.strip()
        expression = expression_value.strip()
        self._validate(name, expression)
        existing = self.repository.find_manual(table_id, name)
        if existing is not None and existing.id != row.id:
            raise MetricAlreadyExistsError()
        row.table_id = table_id
        row.name = name
        row.expression = expression
        self._apply_editable(row, values)
        self._replace_domains(row, domain_ids)
        self.session.flush()
        return self._metric(row, self.domains.read_one(row.id))

    def delete_metric(self, metric_id: UUID) -> None:
        row = self.repository.get(metric_id)
        if row is None:
            raise MetricNotFoundError()
        if row.origin != "manual":
            raise MetricReadOnlyError()
        self.session.delete(row)
        self.session.flush()

    def list_databases(self) -> list[dict[str, Any]]:
        return [self._database(row) for row in self.repository.databases()]

    def list_users(self) -> list[dict[str, Any]]:
        return [
            {
                "id": row.id,
                "source_url": row.source_url,
                "source_id": row.source_id,
                "username": row.username,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "email": row.email,
            }
            for row in self.repository.users()
        ]

    def link_database(
        self, database_id: UUID, connection_id: UUID | None
    ) -> dict[str, Any]:
        row = self.repository.database(database_id)
        if row is None:
            raise SupersetDatabaseNotFoundError()
        if (
            connection_id is not None
            and self.session.get(DatabaseConnection, connection_id) is None
        ):
            raise InvalidMetricError("Connection của standalone không tồn tại.")
        if connection_id is not None and row.backend not in (None, "postgresql"):
            raise InvalidMetricError(
                "Standalone hiện chỉ hỗ trợ liên kết database PostgreSQL."
            )
        row.connection_id = connection_id
        for metric in self.repository.metrics_for_source(row.source_url).values():
            if metric.source_database_id == row.id:
                metric.table_id = self._matched_table_id(
                    row, metric.source_schema, metric.source_table, metric.source_sql
                )
        self.session.flush()
        return self._database(row)

    def sync_superset(
        self, source_url: str, snapshot: SupersetSnapshot
    ) -> dict[str, int]:
        source_url = source_url.rstrip("/")
        users = self.repository.users_for_source(source_url)
        databases = self.repository.databases_for_source(source_url)
        metrics = self.repository.metrics_for_source(source_url)
        for data in snapshot.users:
            source_id = self._positive_id(data.get("id"))
            row = users.get(source_id)
            if row is None:
                row = SupersetUser(
                    source_url=source_url, source_id=source_id, username=""
                )
                self.session.add(row)
                users[source_id] = row
            row.username = self._required_string(data.get("username"), 255)
            row.first_name = self._optional_string(data.get("first_name"), 255)
            row.last_name = self._optional_string(data.get("last_name"), 255)
            row.email = self._optional_string(data.get("email"), 320)
        for data in snapshot.databases:
            source_id = self._positive_id(data.get("id"))
            row = databases.get(source_id)
            if row is None:
                row = SupersetDatabase(
                    source_url=source_url, source_id=source_id, name=""
                )
                self.session.add(row)
                databases[source_id] = row
            row.name = self._required_string(data.get("database_name"), 255)
            row.backend = self._optional_string(data.get("backend"), 64)
        self.session.flush()
        seen: set[int] = set()
        for dataset in snapshot.datasets:
            dataset_id = self._positive_id(dataset.get("id"))
            database_value = dataset.get("database")
            database_id = (
                database_value.get("id")
                if isinstance(database_value, dict)
                else database_value
            )
            database_id = database_id or dataset.get("database_id")
            database = databases.get(self._positive_id(database_id))
            if database is None:
                raise InvalidMetricError(
                    "Dataset trỏ đến database Superset chưa được đồng bộ."
                )
            schema = self._optional_string(dataset.get("schema"), 255)
            table = self._required_string(dataset.get("table_name"), 255)
            source_sql = self._optional_string(dataset.get("sql"), None)
            metric_rows = dataset.get("metrics", [])
            if not isinstance(metric_rows, list):
                raise InvalidMetricError("Danh sách metric Superset không hợp lệ.")
            for data in metric_rows:
                source_id = self._positive_id(data.get("id"))
                if source_id in seen:
                    raise InvalidMetricError("Superset trả về ID metric trùng lặp.")
                seen.add(source_id)
                row = metrics.get(source_id)
                if row is None:
                    row = Metric(
                        origin="superset",
                        source_url=source_url,
                        source_metric_id=source_id,
                    )
                    self.session.add(row)
                    metrics[source_id] = row
                row.name = self._required_string(data.get("metric_name"), 255)
                row.expression = self._required_string(data.get("expression"), None)
                row.label = self._optional_string(data.get("verbose_name"), 255)
                row.description = self._optional_string(data.get("description"), None)
                row.format = self._optional_string(data.get("d3format"), 128)
                row.currency = self._optional_string(data.get("currency"), 16)
                row.metric_type = self._optional_string(data.get("metric_type"), 64)
                row.warning_text = self._optional_string(data.get("warning_text"), None)
                row.source_dataset_id = dataset_id
                row.source_database_id = database.id
                row.source_schema = schema
                row.source_table = table
                row.source_sql = source_sql
                creator = data.get("created_by")
                creator_id = creator.get("id") if isinstance(creator, dict) else None
                row.source_user_id = (
                    users[creator_id].id if creator_id in users else None
                )
                owner = dataset.get("created_by")
                owner_id = owner.get("id") if isinstance(owner, dict) else None
                row.source_dataset_owner_id = (
                    users[owner_id].id if owner_id in users else None
                )
                row.table_id = self._matched_table_id(
                    database, schema, table, source_sql
                )
                row.is_active = True
        for source_id, row in metrics.items():
            if source_id not in seen:
                row.is_active = False
        self.session.flush()
        return {
            "users": len(snapshot.users),
            "databases": len(snapshot.databases),
            "metrics": len(seen),
            "deactivated": sum(1 for source_id in metrics if source_id not in seen),
        }

    def _matched_table_id(
        self,
        database: SupersetDatabase,
        schema: str | None,
        table: str | None,
        source_sql: str | None,
    ) -> UUID | None:
        if database.connection_id is None or table is None or source_sql:
            return None
        matched = self.repository.local_table(database.connection_id, schema, table)
        return matched.id if matched is not None else None

    def _require_table(self, table_id: UUID | None) -> None:
        if table_id is None or self.session.get(DatabaseTable, table_id) is None:
            raise InvalidMetricError(
                "Bảng của metric không tồn tại trong metadata standalone."
            )

    def _domain_ids(self, domain_ids: list[UUID]) -> list[UUID]:
        if self.domains.unknown(domain_ids):
            raise InvalidMetricError("Miền nghiệp vụ không tồn tại.")
        return list(dict.fromkeys(domain_ids))

    def _replace_domains(self, row: Metric, domain_ids: list[UUID] | None) -> None:
        if domain_ids is None or self.domains.ids(row.id) == set(domain_ids):
            return
        self.domains.replace(row.id, domain_ids)
        # The join table is not an ORM entity; touching the row lets the ingestion trigger see the change.
        row.updated_at = utc_now()

    @staticmethod
    def _validate(name: str, expression: str) -> None:
        if (
            not name
            or len(name) > 255
            or not expression
            or len(expression) > 10000
            or ";" in expression
        ):
            raise InvalidMetricError("Tên hoặc biểu thức metric không hợp lệ.")

    @staticmethod
    def _positive_id(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidMetricError("ID từ Superset không hợp lệ.")
        return value

    @staticmethod
    def _required_string(value: Any, max_length: int | None) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or (max_length is not None and len(value) > max_length)
        ):
            raise InvalidMetricError("Trường bắt buộc từ Superset không hợp lệ.")
        return value.strip()

    @staticmethod
    def _optional_string(value: Any, max_length: int | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or (
            max_length is not None and len(value) > max_length
        ):
            raise InvalidMetricError("Trường từ Superset không hợp lệ.")
        return value.strip() or None

    @staticmethod
    def _apply_editable(row: Metric, values: dict[str, Any]) -> None:
        for field in (
            "label",
            "description",
            "format",
            "currency",
            "metric_type",
            "warning_text",
        ):
            if field in values:
                setattr(row, field, values[field])

    @staticmethod
    def _metric(row: Metric, domains: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            key: getattr(row, key)
            for key in (
                "id",
                "origin",
                "name",
                "label",
                "expression",
                "description",
                "format",
                "currency",
                "metric_type",
                "warning_text",
                "is_active",
                "table_id",
                "source_url",
                "source_metric_id",
                "source_dataset_id",
                "source_database_id",
                "source_user_id",
                "source_dataset_owner_id",
                "source_schema",
                "source_table",
                "source_sql",
            )
        } | {"business_domains": domains, "created_at": row.created_at, "updated_at": row.updated_at}

    @staticmethod
    def _database(row: SupersetDatabase) -> dict[str, Any]:
        return {
            key: getattr(row, key)
            for key in (
                "id",
                "source_url",
                "source_id",
                "name",
                "backend",
                "connection_id",
            )
        }
