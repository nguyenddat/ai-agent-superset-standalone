from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ..dependencies import get_metadata_service
from ..schemas.schema_database_metadata import (
    ColumnOut,
    SchemaOut,
    SyncOut,
    TableOut,
)
from ..services import MetadataService

router = APIRouter(prefix="/api/v1", tags=["database-metadata"])
MetadataServiceDep = Annotated[MetadataService, Depends(get_metadata_service)]


@router.post("/database-connections/{connection_id}/sync", response_model=SyncOut)
def sync_connection(connection_id: UUID, service: MetadataServiceDep) -> SyncOut:
    result = service.sync(connection_id)
    response = SyncOut.model_validate(result)
    service.session.commit()
    return response


@router.get("/database-connections/{connection_id}/schemas", response_model=list[SchemaOut])
def list_schemas(connection_id: UUID, service: MetadataServiceDep) -> list[SchemaOut]:
    return [SchemaOut.model_validate(item) for item in service.read_schemas(connection_id)]


@router.get("/schemas/{schema_id}/tables", response_model=list[TableOut])
def list_tables(schema_id: UUID, service: MetadataServiceDep) -> list[TableOut]:
    return [TableOut.model_validate(item) for item in service.read_tables(schema_id)]


@router.get("/tables/{table_id}/columns", response_model=list[ColumnOut])
def list_columns(table_id: UUID, service: MetadataServiceDep) -> list[ColumnOut]:
    return [ColumnOut.model_validate(item) for item in service.read_columns(table_id)]
