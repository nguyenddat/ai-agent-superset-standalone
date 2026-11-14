from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_model import utc_now
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.metric_management.models import Metric

from ..models import GlossaryLink, GlossaryRevision, GlossaryTerm
from ..repositories import GlossaryRepository
from ..utils.exceptions import GlossaryConflictError, GlossaryNotFoundError, GlossaryValidationError


class GlossaryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GlossaryRepository(session)

    def list_terms(self, connection_id: UUID) -> list[dict[str, Any]]:
        self._connection(connection_id)
        return [self._serialize(term) for term in self.repository.list(connection_id)]

    def get_term(self, term_id: UUID) -> dict[str, Any]:
        return self._serialize(self._term(term_id))

    def list_revisions(self, term_id: UUID) -> list[dict[str, Any]]:
        term = self._term(term_id)
        return [self._revision(revision) for revision in self.repository.revisions(term.id)]

    def serving_revision(self, term_id: UUID) -> GlossaryRevision | None:
        self._term(term_id)
        return self._serving(self.repository.revisions(term_id))

    def live_links(self, connection_id: UUID, revision_id: UUID) -> list[dict[str, str]]:
        return self._live_links(connection_id, revision_id)

    def create_term(self, values: dict[str, Any]) -> dict[str, Any]:
        connection_id = values["connection_id"]
        self._connection(connection_id)
        name = " ".join(values["canonical_name"].split())
        if not name or self.repository.find_name(connection_id, name.casefold()):
            raise GlossaryConflictError("Tên thuật ngữ đã tồn tại trong kết nối này.")
        content = self._content(values, connection_id, name)
        term = GlossaryTerm(
            connection_id=connection_id, canonical_name=name, normalized_name=name.casefold(),
            group_name=self._group(values.get("group_name")),
        )
        self.session.add(term)
        self.session.flush()
        self._add_revision(term.id, 1, content)
        return self._serialize(term)

    def update_term(self, term_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        term = self._term(term_id, lock=True)
        revisions = self.repository.revisions(term.id)
        self._expected(revisions[0], values["expected_revision"])
        content = self._content(values, term.connection_id, term.canonical_name)
        group = self._group(values.get("group_name"))
        content_unchanged = (
            revisions[0].definition == content["definition"]
            and revisions[0].synonyms == content["synonyms"]
            and self._links(revisions[0].id) == content["links"]
        )
        if content_unchanged and revisions[0].status != "revoked":
            if term.group_name != group:
                term.group_name = group
                term.updated_at = utc_now()
                self.session.flush()
            return self._serialize(term)
        term.group_name = group
        term.updated_at = utc_now()
        self._add_revision(term.id, revisions[0].number + 1, content)
        return self._serialize(term)

    def approve(self, term_id: UUID, expected_revision: int) -> dict[str, Any]:
        term = self._term(term_id, lock=True)
        revisions = self.repository.revisions(term.id)
        current = revisions[0]
        self._expected(current, expected_revision)
        if current.status != "draft":
            raise GlossaryConflictError("Chỉ có thể duyệt bản nháp hiện tại.")
        current.status = "approved"
        term.updated_at = utc_now()
        self.session.flush()
        return self._serialize(term)

    def revoke(self, term_id: UUID, expected_revision: int) -> dict[str, Any]:
        term = self._term(term_id, lock=True)
        revisions = self.repository.revisions(term.id)
        self._expected(revisions[0], expected_revision)
        serving = self._serving(revisions)
        if serving is None:
            raise GlossaryConflictError("Thuật ngữ chưa có bản được duyệt để thu hồi.")
        term.updated_at = utc_now()
        self._add_revision(term.id, revisions[0].number + 1, {
            "definition": serving.definition, "synonyms": list(serving.synonyms),
            "links": self._links(serving.id),
        }, status="revoked")
        return self._serialize(term)

    def delete_term(self, term_id: UUID) -> None:
        term = self._term(term_id, lock=True)
        self.session.delete(term)
        self.session.flush()

    def discovery(self, connection_id: UUID) -> list[dict[str, Any]]:
        self._connection(connection_id)
        result = []
        for term in self.repository.list(connection_id):
            serving = self._serving(self.repository.revisions(term.id))
            if serving is not None:
                result.append({
                    "id": term.id, "name": term.canonical_name, "definition": serving.definition,
                    "synonyms": serving.synonyms, "links": self._live_links(term.connection_id, serving.id),
                })
        return result

    def _content(self, values: dict[str, Any], connection_id: UUID, name: str) -> dict[str, Any]:
        definition = values["definition"].strip()
        if not definition:
            raise GlossaryValidationError("Cần nhập định nghĩa thuật ngữ.")
        synonyms = []
        seen = {name.casefold()}
        for raw in values["synonyms"]:
            synonym = " ".join(raw.split())
            normalized = synonym.casefold()
            if not synonym or len(synonym) > 255 or normalized in seen:
                raise GlossaryValidationError("Từ đồng nghĩa trống hoặc trùng lặp.")
            seen.add(normalized)
            synonyms.append(synonym)
        links = []
        seen_links = set()
        for item in values["links"]:
            link = item if isinstance(item, dict) else item.model_dump()
            key = (link["kind"], link["id"])
            if key in seen_links:
                raise GlossaryValidationError("Liên kết thuật ngữ bị trùng.")
            seen_links.add(key)
            self._validate_link(connection_id, *key)
            links.append({"kind": link["kind"], "id": str(link["id"])})
        links.sort(key=lambda link: (link["kind"], link["id"]))
        return {"definition": definition, "synonyms": synonyms, "links": links}

    def _add_revision(self, term_id: UUID, number: int, content: dict[str, Any], status: str = "draft") -> None:
        revision = GlossaryRevision(
            term_id=term_id, number=number, definition=content["definition"],
            synonyms=content["synonyms"], status=status,
        )
        self.session.add(revision)
        self.session.flush()
        for link in content["links"]:
            self.session.add(GlossaryLink(
                revision_id=revision.id, kind=link["kind"],
                **{f"{link['kind']}_id": UUID(link["id"])},
            ))
        self.session.flush()

    def _links(self, revision_id: UUID) -> list[dict[str, str]]:
        links = [
            {"kind": link.kind, "id": str(getattr(link, f"{link.kind}_id"))}
            for link in self.repository.links(revision_id)
        ]
        return sorted(links, key=lambda link: (link["kind"], link["id"]))

    def _live_links(self, connection_id: UUID, revision_id: UUID) -> list[dict[str, str]]:
        result = []
        for link in self._links(revision_id):
            try:
                self._validate_link(connection_id, link["kind"], UUID(link["id"]))
            except GlossaryValidationError:
                continue
            result.append(link)
        return result

    def _validate_link(self, connection_id: UUID, kind: str, object_id: UUID) -> None:
        if kind == "table":
            table_id = object_id
        elif kind == "column":
            column = self.session.get(DatabaseColumn, object_id)
            table_id = column.table_id if column else None
        else:
            metric = self.session.get(Metric, object_id)
            table_id = metric.table_id if metric and metric.is_active else None
        if table_id is None:
            raise GlossaryValidationError("Liên kết phải trỏ đến bảng, cột hoặc metric còn tồn tại.")
        owner = self.session.scalar(
            select(DatabaseSchema.connection_id).join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(DatabaseTable.id == table_id)
        )
        if owner != connection_id:
            raise GlossaryValidationError("Liên kết không thuộc kết nối đang chọn.")

    def _connection(self, connection_id: UUID) -> None:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise GlossaryValidationError("Kết nối không tồn tại.")

    def _term(self, term_id: UUID, lock: bool = False) -> GlossaryTerm:
        term = self.repository.get(term_id, lock)
        if term is None:
            raise GlossaryNotFoundError()
        return term

    @staticmethod
    def _group(value: str | None) -> str | None:
        group = " ".join(value.split()) if value else None
        return group or None

    @staticmethod
    def _expected(current: GlossaryRevision, expected: int) -> None:
        if current.number != expected:
            raise GlossaryConflictError()

    @staticmethod
    def _serving(revisions: list[GlossaryRevision]) -> GlossaryRevision | None:
        for revision in revisions:
            if revision.status == "revoked":
                return None
            if revision.status == "approved":
                return revision
        return None

    def _serialize(self, term: GlossaryTerm) -> dict[str, Any]:
        revisions = self.repository.revisions(term.id)
        return {
            "id": term.id, "connection_id": term.connection_id,
            "canonical_name": term.canonical_name, "group_name": term.group_name,
            "current": self._revision(revisions[0]),
            "serving": self._revision(serving) if (serving := self._serving(revisions)) else None,
            "created_at": term.created_at, "updated_at": term.updated_at,
        }

    def _revision(self, revision: GlossaryRevision) -> dict[str, Any]:
        return {
            "number": revision.number, "status": revision.status, "definition": revision.definition,
            "synonyms": revision.synonyms, "links": self._links(revision.id), "created_at": revision.created_at,
        }
