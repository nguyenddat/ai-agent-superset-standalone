from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from ..dependencies import get_conversation_service
from ..schemas.schema_conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListItem,
    ConversationOut,
    ConversationUpdate,
    FeedbackIn,
    FeedbackOut,
    TurnOut,
    ViewIn,
    ViewOut,
)
from ..services import ConversationService

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
ServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
UserQuery = Annotated[str, Query(min_length=1, max_length=255)]
LimitQuery = Annotated[int, Query(ge=1, le=200)]
OffsetQuery = Annotated[int, Query(ge=0)]
TurnsLimitQuery = Annotated[int, Query(ge=1, le=500)]
ResultIdPath = Annotated[str, Path(max_length=32, pattern=r"^\d+-\d+$")]


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationCreate, service: ServiceDep) -> dict[str, Any]:
    result = service.create(body.model_dump())
    service.session.commit()
    return result


@router.get("", response_model=list[ConversationListItem])
def list_conversations(
    user_id: UserQuery, service: ServiceDep, connection_id: UUID | None = None, archived: bool = False,
    q: Annotated[str | None, Query(max_length=200)] = None, limit: LimitQuery = 50, offset: OffsetQuery = 0,
) -> list[dict[str, Any]]:
    return service.list_conversations(user_id, connection_id, archived, q, limit, offset)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID, user_id: UserQuery, service: ServiceDep,
    turns_limit: TurnsLimitQuery = 100, turns_offset: OffsetQuery = 0,
) -> dict[str, Any]:
    return service.detail(conversation_id, user_id, turns_limit, turns_offset)


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: UUID, body: ConversationUpdate, service: ServiceDep) -> dict[str, Any]:
    result = service.update(conversation_id, body.model_dump(exclude_none=True))
    service.session.commit()
    return result


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, user_id: UserQuery, service: ServiceDep) -> Response:
    service.delete(conversation_id, user_id)
    service.session.commit()
    return Response(status_code=204)


@router.get("/{conversation_id}/turns", response_model=list[TurnOut])
def list_turns(
    conversation_id: UUID, user_id: UserQuery, service: ServiceDep,
    limit: TurnsLimitQuery = 100, offset: OffsetQuery = 0,
) -> list[dict[str, Any]]:
    return service.list_turns(conversation_id, user_id, limit, offset)


@router.get("/{conversation_id}/turns/{turn_id}", response_model=TurnOut)
def get_turn(conversation_id: UUID, turn_id: UUID, user_id: UserQuery, service: ServiceDep) -> dict[str, Any]:
    return service.get_turn(conversation_id, turn_id, user_id)


@router.delete("/{conversation_id}/turns/{turn_id}", status_code=204)
def delete_turn(conversation_id: UUID, turn_id: UUID, user_id: UserQuery, service: ServiceDep) -> Response:
    service.delete_turn(conversation_id, turn_id, user_id)
    service.session.commit()
    return Response(status_code=204)


@router.put("/{conversation_id}/turns/{turn_id}/feedback", response_model=FeedbackOut)
def put_feedback(conversation_id: UUID, turn_id: UUID, body: FeedbackIn, service: ServiceDep) -> dict[str, Any]:
    result = service.put_feedback(conversation_id, turn_id, body.model_dump())
    service.session.commit()
    return result


@router.delete("/{conversation_id}/turns/{turn_id}/feedback", status_code=204)
def delete_feedback(conversation_id: UUID, turn_id: UUID, user_id: UserQuery, service: ServiceDep) -> Response:
    service.delete_feedback(conversation_id, turn_id, user_id)
    service.session.commit()
    return Response(status_code=204)


@router.put("/{conversation_id}/turns/{turn_id}/views/{result_id}", response_model=ViewOut)
def put_view(
    conversation_id: UUID, turn_id: UUID, result_id: ResultIdPath, body: ViewIn, service: ServiceDep,
) -> dict[str, Any]:
    result = service.put_view(conversation_id, turn_id, result_id, body.user_id, body.chart)
    service.session.commit()
    return result


@router.delete("/{conversation_id}/turns/{turn_id}/views/{result_id}", status_code=204)
def delete_view(
    conversation_id: UUID, turn_id: UUID, result_id: ResultIdPath, user_id: UserQuery, service: ServiceDep,
) -> Response:
    service.delete_view(conversation_id, turn_id, result_id, user_id)
    service.session.commit()
    return Response(status_code=204)
