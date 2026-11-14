from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import BusinessModelService


def get_business_model_service(session: Annotated[Session, Depends(get_database)]) -> BusinessModelService:
    return BusinessModelService(session)
