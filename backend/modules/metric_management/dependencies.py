from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import MetricService


def get_metric_service(
    session: Annotated[Session, Depends(get_database)],
) -> MetricService:
    return MetricService(session)
