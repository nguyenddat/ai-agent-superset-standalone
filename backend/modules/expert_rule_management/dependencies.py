from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import ExpertRuleService


def get_expert_rule_service(session: Annotated[Session, Depends(get_database)]) -> ExpertRuleService:
    return ExpertRuleService(session)
