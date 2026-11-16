from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .vector_store.ingestion.registry import validate_topics

JobStatus = Literal["pending", "running", "succeeded", "failed", "superseded"]


class TopicSelection(BaseModel):
    connection_id: UUID
    topics: list[str] | None = None

    @field_validator("topics")
    @classmethod
    def known_topics(cls, value: list[str] | None) -> list[str] | None:
        return list(validate_topics(value)) if value is not None else None


class SyncIn(TopicSelection):
    pass


class SyncOut(BaseModel):
    connection_id: UUID
    topics: list[str]
    total: int
    indexed: int
    unchanged: int
    deleted: int


class JobEnqueueIn(TopicSelection):
    pass


class JobEnqueueOut(BaseModel):
    connection_id: UUID
    topics: list[str]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    topic: str
    source: str
    status: JobStatus
    attempts: int
    run_after: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    result: dict | None
    created_at: datetime


class RetrieveIn(BaseModel):
    connection_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Câu hỏi không được để trống.")
        return value


class CandidateOut(BaseModel):
    metric_id: UUID
    table_id: UUID
    name: str
    label: str | None
    description: str | None
    score: float
    matched_topics: list[str]


class RetrieveOut(BaseModel):
    candidates: list[CandidateOut]
