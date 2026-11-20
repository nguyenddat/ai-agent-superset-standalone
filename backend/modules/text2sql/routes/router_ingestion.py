from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_database
from backend.modules.database_connection.models import DatabaseConnection

from ..dependencies import IndexServices, get_index_services
from ..models.ingestion_job import MANUAL
from ..repositories import IngestionJobRepository
from ..schemas import (
    CandidateOut,
    JobEnqueueIn,
    JobEnqueueOut,
    JobOut,
    JobStatus,
    RetrieveIn,
    RetrieveOut,
    SyncIn,
    SyncOut,
)
from ..services import IngestionService, RetrievalService
from ..utils.exceptions import Text2SqlConnectionNotFound
from ..utils.topics import TOPICS

router = APIRouter()

ServiceDep = Annotated[IndexServices, Depends(get_index_services)]
SessionDep = Annotated[Session, Depends(get_database)]


@router.post("/ingestion/sync", response_model=SyncOut)
def sync_index(body: SyncIn, services: ServiceDep) -> SyncOut:
    index, embedding, session = services
    result = IngestionService(session, index, embedding).sync(body.connection_id, body.topics or TOPICS)
    return SyncOut(
        connection_id=result.connection_id, topics=list(result.topics), total=result.total,
        indexed=result.indexed, unchanged=result.unchanged, deleted=result.deleted,
    )


@router.post("/ingestion/jobs", response_model=JobEnqueueOut, status_code=status.HTTP_202_ACCEPTED)
def enqueue_ingestion(body: JobEnqueueIn, session: SessionDep) -> JobEnqueueOut:
    if session.get(DatabaseConnection, body.connection_id) is None:
        raise Text2SqlConnectionNotFound()
    topics = body.topics or list(TOPICS)
    IngestionJobRepository(session).enqueue([body.connection_id], topics, MANUAL)
    session.commit()
    return JobEnqueueOut(connection_id=body.connection_id, topics=topics)


@router.get("/ingestion/jobs", response_model=list[JobOut])
def list_ingestion_jobs(
    session: SessionDep,
    connection_id: UUID | None = None,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobOut]:
    jobs = IngestionJobRepository(session).list_recent(connection_id, job_status, limit)
    return [JobOut.model_validate(job) for job in jobs]


@router.post("/retrieve", response_model=RetrieveOut)
def retrieve_metrics(body: RetrieveIn, services: ServiceDep) -> RetrieveOut:
    index, embedding, session = services
    candidates = RetrievalService(session, index, embedding).top_metrics(
        body.connection_id, body.question, body.k
    )
    return RetrieveOut(candidates=[CandidateOut.model_validate(candidate.__dict__) for candidate in candidates])
