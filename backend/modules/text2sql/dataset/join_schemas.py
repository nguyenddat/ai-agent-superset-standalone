from uuid import UUID

from pydantic import BaseModel, Field


class JoinEdge(BaseModel):
    edge_id: UUID = Field(description="ID cột khóa ngoại (cột tham chiếu); dùng làm định danh quan hệ.")
    child_table_id: UUID
    child_column_id: UUID
    parent_table_id: UUID
    parent_column_id: UUID
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    parent_is_unique: bool = Field(description="Cột được tham chiếu là khóa chính hoặc duy nhất (quan hệ nhiều-một).")


class JoinStep(BaseModel):
    alias: str
    table_id: UUID
    table: str
    joined_from: str
    on: str
    edge_id: UUID
    multiplies_rows: bool


class JoinOption(BaseModel):
    signature: str
    root_table_id: UUID
    from_sql: str
    steps: list[JoinStep]
    edge_ids: list[UUID]
    table_ids: list[UUID]
    aliases: dict[str, str]
    warnings: list[str]


class JoinPlan(BaseModel):
    status: str = Field(description="ok, ambiguous hoặc not_declared.")
    options: list[JoinOption] = []
    message: str = ""
