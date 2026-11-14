from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_data_lineage_service
from ..schemas.schema_data_lineage import (
    GraphOut,
    PreviewIn,
    PreviewOut,
    TransformationIn,
    TransformationOut,
    ViewSqlOut,
)
from ..services import DataLineageService

router = APIRouter(prefix="/api/v1/data-lineage", tags=["data-lineage"])
ServiceDep = Annotated[DataLineageService, Depends(get_data_lineage_service)]


@router.get("/connections/{connection_id}/transformations", response_model=list[TransformationOut])
def list_transformations(connection_id: UUID, service: ServiceDep) -> list[TransformationOut]:
    return [TransformationOut.model_validate(item) for item in service.list_transformations(connection_id)]


@router.post("/connections/{connection_id}/transformations", response_model=TransformationOut, status_code=201)
def create_transformation(connection_id: UUID, body: TransformationIn, service: ServiceDep) -> TransformationOut:
    response = TransformationOut.model_validate(service.save_transformation(connection_id, body.model_dump()))
    service.session.commit()
    return response


@router.get("/connections/{connection_id}/transformations/{transformation_id}", response_model=TransformationOut)
def get_transformation(connection_id: UUID, transformation_id: UUID, service: ServiceDep) -> TransformationOut:
    return TransformationOut.model_validate(service.get_transformation(connection_id, transformation_id))


@router.put("/connections/{connection_id}/transformations/{transformation_id}", response_model=TransformationOut)
def update_transformation(
    connection_id: UUID, transformation_id: UUID, body: TransformationIn, service: ServiceDep,
) -> TransformationOut:
    response = TransformationOut.model_validate(service.save_transformation(
        connection_id, body.model_dump(), transformation_id,
    ))
    service.session.commit()
    return response


@router.delete("/connections/{connection_id}/transformations/{transformation_id}", status_code=204)
def delete_transformation(connection_id: UUID, transformation_id: UUID, service: ServiceDep) -> Response:
    service.delete_transformation(connection_id, transformation_id)
    service.session.commit()
    return Response(status_code=204)


@router.post("/connections/{connection_id}/preview", response_model=PreviewOut)
def preview_transformation(connection_id: UUID, body: PreviewIn, service: ServiceDep) -> PreviewOut:
    return PreviewOut.model_validate(service.preview(connection_id, body.target_table_id, body.sql_text))


@router.get("/connections/{connection_id}/tables/{table_id}/view-sql", response_model=ViewSqlOut)
def read_view_sql(connection_id: UUID, table_id: UUID, service: ServiceDep) -> ViewSqlOut:
    return ViewSqlOut.model_validate(service.read_view_sql(connection_id, table_id))


@router.get("/connections/{connection_id}/graph", response_model=GraphOut)
def get_graph(connection_id: UUID, service: ServiceDep) -> GraphOut:
    return GraphOut.model_validate(service.graph(connection_id))
