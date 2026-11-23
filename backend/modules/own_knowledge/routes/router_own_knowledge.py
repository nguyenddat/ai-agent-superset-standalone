from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_own_knowledge_service, require_admin_key, require_agent_key
from ..schemas.schema_own_knowledge import (
    AdminPromote,
    AdminReview,
    AnswerOut,
    ClarificationAnswer,
    ClarificationOut,
    ClarificationPush,
    EntryOut,
    EntryUpdate,
    PromoteOut,
)
from ..services import OwnKnowledgeService

router = APIRouter(prefix="/api/v1/own-knowledge", tags=["own-knowledge"])
ServiceDep = Annotated[OwnKnowledgeService, Depends(get_own_knowledge_service)]
AgentDep = Annotated[None, Depends(require_agent_key)]
AdminDep = Annotated[None, Depends(require_admin_key)]


@router.post("/clarifications", response_model=ClarificationOut, status_code=201)
def push_clarification(body: ClarificationPush, service: ServiceDep, _auth: AgentDep) -> dict[str, Any]:
    result = service.push_clarification(body.model_dump())
    service.session.commit()
    return result


@router.get("/clarifications/{clarification_id}", response_model=ClarificationOut)
def get_clarification(clarification_id: UUID, user_id: str, service: ServiceDep, _auth: AgentDep) -> dict[str, Any]:
    return service.get_clarification(clarification_id, user_id)


@router.post("/clarifications/{clarification_id}/answer", response_model=AnswerOut)
def answer_clarification(
    clarification_id: UUID, body: ClarificationAnswer, service: ServiceDep, _auth: AgentDep,
) -> dict[str, Any]:
    result = service.answer_clarification(clarification_id, body.model_dump())
    service.session.commit()
    return result


@router.get("/agent/entries", response_model=list[EntryOut])
def list_agent_entries(connection_id: UUID, user_id: str, service: ServiceDep, _auth: AgentDep) -> list[dict[str, Any]]:
    return service.agent_entries(connection_id, user_id)


@router.put("/agent/entries/{entry_id}", response_model=EntryOut)
def update_own_entry(entry_id: UUID, body: EntryUpdate, service: ServiceDep, _auth: AgentDep) -> dict[str, Any]:
    result = service.update_own_entry(entry_id, body.model_dump())
    service.session.commit()
    return result


@router.delete("/agent/entries/{entry_id}", status_code=204)
def delete_own_entry(entry_id: UUID, user_id: str, service: ServiceDep, _auth: AgentDep) -> Response:
    service.delete_own_entry(entry_id, user_id)
    service.session.commit()
    return Response(status_code=204)


@router.get("/admin/entries", response_model=list[EntryOut])
def list_review_entries(
    service: ServiceDep, _auth: AdminDep, connection_id: UUID | None = None,
    status: Literal["pending", "kept_own", "promoted"] | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    return service.review_entries(connection_id, status, user_id)


@router.get("/admin/entries/{entry_id}", response_model=EntryOut)
def get_review_entry(entry_id: UUID, service: ServiceDep, _auth: AdminDep) -> dict[str, Any]:
    return service.get_admin_entry(entry_id)


@router.post("/admin/entries/{entry_id}/review", response_model=EntryOut)
def review_entry(entry_id: UUID, body: AdminReview, service: ServiceDep, _auth: AdminDep) -> dict[str, Any]:
    result = service.review_entry(entry_id, body.model_dump())
    service.session.commit()
    return result


@router.post("/admin/entries/{entry_id}/promote", response_model=PromoteOut)
def promote_entry(entry_id: UUID, body: AdminPromote, service: ServiceDep, _auth: AdminDep) -> dict[str, Any]:
    result = service.promote_entry(entry_id, body.model_dump())
    service.session.commit()
    return result
