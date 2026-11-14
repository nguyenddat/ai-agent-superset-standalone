import hmac
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from backend.core.database import get_database
from backend.core.setting import config

from .services import OwnKnowledgeService
from .utils.exceptions import OwnKnowledgeNotConfiguredError, OwnKnowledgeUnauthorizedError


def _check_key(provided: str | None, role: str) -> None:
    agent = config.own_knowledge_agent_key
    admin = config.own_knowledge_admin_key
    if agent is None or admin is None:
        raise OwnKnowledgeNotConfiguredError()
    agent_value = agent.get_secret_value()
    admin_value = admin.get_secret_value()
    if len(agent_value) < 32 or len(admin_value) < 32 or hmac.compare_digest(agent_value, admin_value):
        raise OwnKnowledgeNotConfiguredError()
    expected = agent_value if role == "agent" else admin_value
    if provided is None or not hmac.compare_digest(provided, expected):
        raise OwnKnowledgeUnauthorizedError()


def require_agent_key(x_own_knowledge_key: Annotated[str | None, Header()] = None) -> None:
    _check_key(x_own_knowledge_key, "agent")


def require_admin_key(x_own_knowledge_key: Annotated[str | None, Header()] = None) -> None:
    _check_key(x_own_knowledge_key, "admin")


def get_own_knowledge_service(session: Annotated[Session, Depends(get_database)]) -> OwnKnowledgeService:
    return OwnKnowledgeService(session)
