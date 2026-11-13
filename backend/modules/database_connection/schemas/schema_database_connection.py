from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectionTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialect: Literal["postgresql"]
    driver: Literal["psycopg"] | None = None
    uri: str = Field(min_length=1)


class ConnectionCreateIn(ConnectionTestIn):
    name: str = Field(min_length=1, max_length=255)


class ConnectionPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    uri: str | None = Field(default=None, min_length=1)


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    dialect: str
    driver: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConnectionTestOut(BaseModel):
    ok: bool
    message: str


class DialectOut(BaseModel):
    dialect: str
    driver: str
    label: str
