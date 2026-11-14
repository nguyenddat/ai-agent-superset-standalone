import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.common.base_model import utc_now
from backend.modules.database_connection.models import DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.models import ExpertRule
from backend.modules.expert_rule_management.schemas.schema_expert_rule import RuleCreate
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.models import GlossaryTerm
from backend.modules.glossary_management.schemas.schema_glossary import GlossaryCreate
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric
from backend.modules.metric_management.schemas.schema_metric import MetricIn
from backend.modules.metric_management.services import MetricService

from ..models import OwnClarification, OwnKnowledgeEntry, OwnProposal
from ..repositories import OwnKnowledgeRepository
from ..utils.exceptions import OwnKnowledgeConflictError, OwnKnowledgeNotFoundError, OwnKnowledgeValidationError


class OwnKnowledgeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OwnKnowledgeRepository(session)

    def push_clarification(self, values: dict[str, Any]) -> dict[str, Any]:
        connection_id = values["connection_id"]
        self._connection(connection_id)
        user_id = self._text(values["user_id"], 255)
        key = self._text(values["idempotency_key"], 128)
        question = self._text(values["question"], 10000)
        missing = sorted(set(values["missing"]))
        if len(missing) != len(values["missing"]):
            raise OwnKnowledgeValidationError("Loại nội dung thiếu bị trùng.")
        proposals = []
        seen = set()
        for item in values["proposals"]:
            proposal = item if isinstance(item, dict) else item.model_dump()
            name = self._name(proposal["name"], 255)
            kind = proposal["kind"]
            if kind not in missing or (kind, name.casefold()) in seen:
                raise OwnKnowledgeValidationError("Đề xuất trùng hoặc không thuộc loại nội dung thiếu.")
            seen.add((kind, name.casefold()))
            options = [self._text(option, 2000) for option in proposal["options"]]
            if len({option.casefold() for option in options}) != len(options):
                raise OwnKnowledgeValidationError("Phương án làm rõ bị trùng.")
            table_id = proposal.get("table_id")
            if table_id is not None:
                self._table(connection_id, table_id)
            proposals.append({
                "kind": kind, "name": name, "normalized_name": name.casefold(),
                "concept": self._optional_text(proposal.get("concept"), 255),
                "prompt": self._text(proposal["prompt"], 2000), "options": options,
                "table_id": table_id,
            })
        canonical = {
            "user_id": user_id, "connection_id": str(connection_id), "idempotency_key": key,
            "source_session_id": self._optional_text(values.get("source_session_id"), 255),
            "source_question_id": self._optional_text(values.get("source_question_id"), 255),
            "question": question, "missing": missing,
            "proposals": [{**item, "table_id": str(item["table_id"]) if item["table_id"] else None}
                          for item in proposals],
        }
        fingerprint = self._fingerprint(canonical)
        existing = self.repository.by_key(connection_id, user_id, key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise OwnKnowledgeConflictError("Khóa chống gửi trùng đã dùng cho nội dung khác.")
            return self._clarification(existing)
        try:
            with self.session.begin_nested():
                clarification = OwnClarification(
                    connection_id=connection_id, user_id=user_id, idempotency_key=key,
                    source_session_id=canonical["source_session_id"],
                    source_question_id=canonical["source_question_id"],
                    question=question, missing=missing, status="pending", request_fingerprint=fingerprint,
                )
                self.session.add(clarification)
                self.session.flush()
                for item in proposals:
                    self.session.add(OwnProposal(clarification_id=clarification.id, **item))
                self.session.flush()
        except IntegrityError as error:
            existing = self.repository.by_key(connection_id, user_id, key)
            if existing is None or existing.request_fingerprint != fingerprint:
                raise OwnKnowledgeConflictError("Khóa chống gửi trùng hoặc đề xuất đã tồn tại.") from error
            return self._clarification(existing)
        return self._clarification(clarification)

    def get_clarification(self, clarification_id: UUID, user_id: str) -> dict[str, Any]:
        return self._clarification(self._own_clarification(clarification_id, user_id))

    def answer_clarification(self, clarification_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        clarification = self._own_clarification(clarification_id, values["user_id"], lock=True)
        proposals = {item.id: item for item in self.repository.proposals(clarification.id)}
        answers = []
        seen = set()
        for item in values["answers"]:
            answer = item if isinstance(item, dict) else item.model_dump()
            proposal_id = answer["proposal_id"]
            if proposal_id in seen or proposal_id not in proposals:
                raise OwnKnowledgeValidationError("Phương án xác nhận không thuộc câu hỏi hoặc bị trùng.")
            seen.add(proposal_id)
            proposal = proposals[proposal_id]
            index = answer.get("option_index")
            if index is not None:
                if index >= len(proposal.options):
                    raise OwnKnowledgeValidationError("Chỉ số phương án làm rõ không hợp lệ.")
                definition = proposal.options[index]
            else:
                definition = self._text(answer["definition"], 2000)
            answers.append({"proposal_id": str(proposal_id), "definition": definition})
        answers.sort(key=lambda item: item["proposal_id"])
        fingerprint = self._fingerprint({"state": values["state"], "answers": answers})
        if clarification.status != "pending":
            if clarification.answer_fingerprint != fingerprint:
                raise OwnKnowledgeConflictError("Câu hỏi đã được trả lời bằng nội dung khác.")
            return self._answer_result(clarification)
        confirmed_entries = []
        if values["state"] == "confirmed":
            for answer in answers:
                proposal = proposals[UUID(answer["proposal_id"])]
                entry = self.repository.own_entry(
                    clarification.connection_id, clarification.user_id, proposal.kind, proposal.normalized_name,
                )
                if entry is None:
                    entry = OwnKnowledgeEntry(
                        connection_id=clarification.connection_id, user_id=clarification.user_id,
                        kind=proposal.kind, normalized_name=proposal.normalized_name,
                    )
                    self.session.add(entry)
                else:
                    entry.version += 1
                entry.name = proposal.name
                entry.concept = proposal.concept
                entry.definition = answer["definition"]
                entry.table_id = proposal.table_id
                entry.source_clarification_id = clarification.id
                entry.source_proposal_id = proposal.id
                self._reopen(entry)
                confirmed_entries.append(entry)
        self.session.flush()
        clarification.confirmed_entry_ids = [str(entry.id) for entry in confirmed_entries]
        clarification.status = values["state"]
        clarification.answer_fingerprint = fingerprint
        clarification.answered_at = utc_now()
        self.session.flush()
        return self._answer_result(clarification)

    def agent_entries(self, connection_id: UUID, user_id: str) -> list[dict[str, Any]]:
        self._connection(connection_id)
        return [self._entry(entry) for entry in self.repository.own_entries(connection_id, self._text(user_id, 255))
                if self._active_for_agent(entry)]

    def update_own_entry(self, entry_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        entry = self._own_entry(entry_id, values["user_id"], lock=True)
        self._expected(entry, values["expected_version"])
        name = self._name(values["name"], 255)
        normalized = name.casefold()
        duplicate = self.repository.own_entry(entry.connection_id, entry.user_id, entry.kind, normalized)
        if duplicate is not None and duplicate.id != entry.id:
            raise OwnKnowledgeConflictError("Tên nội dung riêng đã tồn tại.")
        entry.name = name
        entry.normalized_name = normalized
        entry.concept = self._optional_text(values.get("concept"), 255)
        entry.definition = self._text(values["definition"], 2000)
        entry.version += 1
        self._reopen(entry)
        self.session.flush()
        return self._entry(entry)

    def delete_own_entry(self, entry_id: UUID, user_id: str) -> None:
        self.session.delete(self._own_entry(entry_id, user_id, lock=True))
        self.session.flush()

    def review_entries(
        self, connection_id: UUID | None, status: str | None, user_id: str | None,
    ) -> list[dict[str, Any]]:
        if connection_id is not None:
            self._connection(connection_id)
        return [self._entry(entry) for entry in self.repository.review_entries(connection_id, status, user_id)]

    def get_admin_entry(self, entry_id: UUID) -> dict[str, Any]:
        return self._entry(self._get_entry(entry_id))

    def review_entry(self, entry_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        entry = self._get_entry(entry_id, lock=True)
        self._expected(entry, values["expected_version"])
        entry.review_status = "kept_own" if values["action"] == "keep_own" else "pending"
        entry.review_note = self._optional_text(values.get("note"), 1000)
        entry.reviewed_by = self._text(values["reviewer_id"], 255)
        entry.reviewed_at = utc_now()
        entry.promoted_kind = None
        entry.promoted_id = None
        entry.version += 1
        entry.updated_at = utc_now()
        self.session.flush()
        return self._entry(entry)

    def promote_entry(self, entry_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        entry = self._get_entry(entry_id, lock=True)
        self._expected(entry, values["expected_version"])
        if entry.review_status == "promoted":
            raise OwnKnowledgeConflictError("Nội dung đã được chuyển thành bản ghi hệ thống.")
        payload = values["payload"]
        if not isinstance(payload, dict):
            raise OwnKnowledgeValidationError("Payload hệ thống không hợp lệ.")
        kind = values["target_kind"]
        try:
            if kind == "glossary":
                body = GlossaryCreate.model_validate({**payload, "connection_id": entry.connection_id})
                saved = GlossaryService(self.session).create_term(body.model_dump())
            elif kind == "metric":
                body = MetricIn.model_validate(payload)
                self._table(entry.connection_id, body.table_id)
                saved = MetricService(self.session).create_metric(body.model_dump())
            else:
                body = RuleCreate.model_validate({**payload, "connection_id": entry.connection_id})
                saved = ExpertRuleService(self.session).create_rule(body.model_dump())
        except PydanticValidationError as error:
            raise OwnKnowledgeValidationError("Payload hệ thống không hợp lệ.") from error
        entry.review_status = "promoted"
        entry.review_note = self._optional_text(values.get("note"), 1000)
        entry.reviewed_by = self._text(values["reviewer_id"], 255)
        entry.reviewed_at = utc_now()
        entry.promoted_kind = kind
        entry.promoted_id = saved["id"]
        entry.version += 1
        entry.updated_at = utc_now()
        self.session.flush()
        return {"entry": self._entry(entry), "target": saved}

    def _active_for_agent(self, entry: OwnKnowledgeEntry) -> bool:
        if entry.review_status != "promoted" or entry.promoted_id is None:
            return True
        if entry.promoted_kind == "glossary":
            term = self.session.get(GlossaryTerm, entry.promoted_id)
            return term is None or GlossaryService(self.session).serving_revision(term.id) is None
        if entry.promoted_kind == "metric":
            metric = self.session.get(Metric, entry.promoted_id)
            if metric is None or not metric.is_active or metric.table_id is None:
                return True
            owner = self.session.scalar(
                select(DatabaseSchema.connection_id).join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
                .where(DatabaseTable.id == metric.table_id)
            )
            return owner != entry.connection_id
        if entry.promoted_kind == "expert_rule":
            rule = self.session.get(ExpertRule, entry.promoted_id)
            return rule is None or not ExpertRuleService(self.session).get_rule(rule.id)["is_discoverable"]
        return True

    def _connection(self, connection_id: UUID) -> None:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise OwnKnowledgeValidationError("Kết nối không tồn tại.")

    def _table(self, connection_id: UUID, table_id: UUID) -> None:
        owner = self.session.scalar(
            select(DatabaseSchema.connection_id).join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(DatabaseTable.id == table_id)
        )
        if owner != connection_id:
            raise OwnKnowledgeValidationError("Bảng không thuộc kết nối đang chọn.")

    def _own_clarification(self, clarification_id: UUID, user_id: str, lock: bool = False) -> OwnClarification:
        clarification = self.repository.clarification(clarification_id, lock)
        if clarification is None or clarification.user_id != self._text(user_id, 255):
            raise OwnKnowledgeNotFoundError()
        return clarification

    def _get_entry(self, entry_id: UUID, lock: bool = False) -> OwnKnowledgeEntry:
        entry = self.repository.entry(entry_id, lock)
        if entry is None:
            raise OwnKnowledgeNotFoundError()
        return entry

    def _own_entry(self, entry_id: UUID, user_id: str, lock: bool = False) -> OwnKnowledgeEntry:
        entry = self._get_entry(entry_id, lock)
        if entry.user_id != self._text(user_id, 255):
            raise OwnKnowledgeNotFoundError()
        return entry

    @staticmethod
    def _expected(entry: OwnKnowledgeEntry, expected: int) -> None:
        if entry.version != expected:
            raise OwnKnowledgeConflictError()

    @staticmethod
    def _reopen(entry: OwnKnowledgeEntry) -> None:
        entry.review_status = "pending"
        entry.review_note = None
        entry.reviewed_by = None
        entry.reviewed_at = None
        entry.promoted_kind = None
        entry.promoted_id = None
        entry.updated_at = utc_now()

    @staticmethod
    def _text(value: str, maximum: int) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > maximum:
            raise OwnKnowledgeValidationError("Văn bản trống hoặc vượt quá giới hạn.")
        return normalized

    @classmethod
    def _name(cls, value: str, maximum: int) -> str:
        return " ".join(cls._text(value, maximum).split())

    @classmethod
    def _optional_text(cls, value: str | None, maximum: int) -> str | None:
        return cls._text(value, maximum) if value and value.strip() else None

    @staticmethod
    def _fingerprint(value: Any) -> str:
        packed = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()

    def _clarification(self, clarification: OwnClarification) -> dict[str, Any]:
        return {
            "id": clarification.id, "user_id": clarification.user_id, "connection_id": clarification.connection_id,
            "idempotency_key": clarification.idempotency_key,
            "source_session_id": clarification.source_session_id,
            "source_question_id": clarification.source_question_id,
            "question": clarification.question, "missing": clarification.missing, "status": clarification.status,
            "proposals": [{
                "id": proposal.id, "kind": proposal.kind, "name": proposal.name, "concept": proposal.concept,
                "prompt": proposal.prompt, "options": proposal.options, "table_id": proposal.table_id,
            } for proposal in self.repository.proposals(clarification.id)],
            "created_at": clarification.created_at, "answered_at": clarification.answered_at,
        }

    def _answer_result(self, clarification: OwnClarification) -> dict[str, Any]:
        entries = [self.repository.entry(UUID(entry_id)) for entry_id in clarification.confirmed_entry_ids]
        return {
            "clarification": self._clarification(clarification),
            "entries": [self._entry(entry) for entry in entries if entry is not None],
        }

    def _entry(self, entry: OwnKnowledgeEntry) -> dict[str, Any]:
        source = self.repository.clarification(entry.source_clarification_id) if entry.source_clarification_id else None
        return {
            "id": entry.id, "connection_id": entry.connection_id, "user_id": entry.user_id,
            "kind": entry.kind, "name": entry.name, "concept": entry.concept,
            "definition": entry.definition, "table_id": entry.table_id,
            "source_clarification_id": entry.source_clarification_id,
            "source_proposal_id": entry.source_proposal_id,
            "source_question": source.question if source else None,
            "review_status": entry.review_status, "review_note": entry.review_note,
            "reviewed_by": entry.reviewed_by, "reviewed_at": entry.reviewed_at,
            "promoted_kind": entry.promoted_kind,
            "promoted_id": entry.promoted_id, "version": entry.version,
            "created_at": entry.created_at, "updated_at": entry.updated_at,
            "active_for_agent": self._active_for_agent(entry),
        }
