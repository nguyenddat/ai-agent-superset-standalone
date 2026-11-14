from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import GlossaryService


def get_glossary_service(session: Annotated[Session, Depends(get_database)]) -> GlossaryService:
    return GlossaryService(session)
