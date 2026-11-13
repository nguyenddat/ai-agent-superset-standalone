from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database
from backend.modules.database_connection.services import ConnectionService, MetadataService


def get_connection_service(session: Annotated[Session, Depends(get_database)]) -> ConnectionService:
    return ConnectionService(session)


def get_metadata_service(session: Annotated[Session, Depends(get_database)]) -> MetadataService:
    return MetadataService(session)
