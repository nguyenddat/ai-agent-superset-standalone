from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import ConversationService


def get_conversation_service(session: Annotated[Session, Depends(get_database)]) -> ConversationService:
    return ConversationService(session)
