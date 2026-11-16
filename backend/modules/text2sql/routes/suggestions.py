from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_database

from ..chat.suggestions import SuggestionService, SuggestionSource

router = APIRouter()

DEFAULT_LIMIT = 6
MAX_LIMIT = 20


class SuggestionOut(BaseModel):
    question: str
    source: SuggestionSource


@router.get("/suggestions", response_model=list[SuggestionOut])
def list_suggestions(
    session: Annotated[Session, Depends(get_database)],
    connection_id: UUID,
    user_id: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[SuggestionOut]:
    items = SuggestionService(session).suggest(connection_id, user_id.strip() if user_id else None, limit)
    return [SuggestionOut(question=item.question, source=item.source) for item in items]
