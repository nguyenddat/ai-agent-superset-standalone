from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ..dependencies import get_connection_service
from ..schemas.schema_database_connection import (
    ConnectionCreateIn,
    ConnectionOut,
    ConnectionPatchIn,
    ConnectionTestIn,
    ConnectionTestOut,
    DialectOut,
)
from ..services import ConnectionService

router = APIRouter(prefix="/api/v1", tags=["database-connections"])
ConnectionServiceDep = Annotated[ConnectionService, Depends(get_connection_service)]


@router.get("/database-connections", response_model=list[ConnectionOut])
def list_connections(
    service: ConnectionServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[ConnectionOut]:
    return [ConnectionOut.model_validate(item) for item in service.list_connections(offset=offset, limit=limit)]


@router.get("/database-connections/dialects", response_model=list[DialectOut])
def list_dialects() -> list[DialectOut]:
    return [DialectOut(dialect="postgresql", driver="psycopg", label="PostgreSQL")]


@router.post("/database-connections/test", response_model=ConnectionTestOut)
def test_connection(body: ConnectionTestIn, service: ConnectionServiceDep) -> ConnectionTestOut:
    service.test_connection(body.uri)
    return ConnectionTestOut(ok=True, message="Kết nối thành công.")


@router.post("/database-connections", response_model=ConnectionOut, status_code=201)
def create_connection(body: ConnectionCreateIn, service: ConnectionServiceDep) -> ConnectionOut:
    result = service.register(name=body.name, uri=body.uri)
    response = ConnectionOut.model_validate(result)
    service.session.commit()
    return response


@router.get("/database-connections/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: UUID, service: ConnectionServiceDep) -> ConnectionOut:
    return ConnectionOut.model_validate(service.get_connection(connection_id))


@router.patch("/database-connections/{connection_id}", response_model=ConnectionOut)
def update_connection(connection_id: UUID, body: ConnectionPatchIn, service: ConnectionServiceDep) -> ConnectionOut:
    result = service.update(connection_id, body.model_dump(exclude_unset=True))
    response = ConnectionOut.model_validate(result)
    service.session.commit()
    return response


@router.delete("/database-connections/{connection_id}", status_code=204)
def delete_connection(connection_id: UUID, service: ConnectionServiceDep) -> Response:
    service.delete(connection_id)
    service.session.commit()
    return Response(status_code=204)
