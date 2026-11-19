from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.business_model.schemas.schema_business_model import DomainRef


class GlossaryLink(BaseModel):
    kind: Literal["table", "column", "metric"]
    id: UUID


class GlossaryContent(BaseModel):
    definition: str = Field(min_length=1, max_length=10000)
    synonyms: list[str] = Field(default_factory=list, max_length=50)
    links: list[GlossaryLink] = Field(default_factory=list, max_length=100)


class GlossaryCreate(GlossaryContent):
    connection_id: UUID
    canonical_name: str = Field(min_length=1, max_length=255)
    business_domain_ids: list[UUID] = Field(default_factory=list, max_length=50)


class GlossaryUpdate(GlossaryContent):
    expected_revision: int = Field(ge=1)
    business_domain_ids: list[UUID] = Field(default_factory=list, max_length=50)


class RevisionOut(BaseModel):
    number: int
    status: Literal["draft", "approved", "revoked"]
    definition: str
    synonyms: list[str]
    links: list[GlossaryLink]
    created_at: datetime


class GlossaryOut(BaseModel):
    id: UUID
    connection_id: UUID
    canonical_name: str
    business_domains: list[DomainRef]
    current: RevisionOut
    serving: RevisionOut | None
    created_at: datetime
    updated_at: datetime


class ReviewIn(BaseModel):
    expected_revision: int = Field(ge=1)
