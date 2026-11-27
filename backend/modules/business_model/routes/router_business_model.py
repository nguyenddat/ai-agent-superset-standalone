from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_business_model_service
from ..schemas.schema_business_model import (
    BusinessModelOut,
    CanvasIn,
    CanvasOut,
    DomainIn,
    DomainOut,
    EdgeIn,
    EdgeOut,
    LayerIn,
    LayerOrderIn,
    LayerOut,
    TableLayerIn,
    TableLayerOut,
)
from ..services import BusinessModelService

router = APIRouter(prefix="/api/v1/business-model", tags=["business-model"])
ServiceDep = Annotated[BusinessModelService, Depends(get_business_model_service)]


@router.get("/layers", response_model=list[LayerOut])
def list_layers(service: ServiceDep) -> list[LayerOut]:
    return [LayerOut.model_validate(layer) for layer in service.list_layers()]


@router.post("/layers", response_model=LayerOut, status_code=201)
def create_layer(body: LayerIn, service: ServiceDep) -> LayerOut:
    response = LayerOut.model_validate(service.create_layer(body.model_dump()))
    service.session.commit()
    return response


@router.put("/layers/order", response_model=list[LayerOut])
def reorder_layers(body: LayerOrderIn, service: ServiceDep) -> list[LayerOut]:
    response = [LayerOut.model_validate(layer) for layer in service.reorder_layers(body.levels)]
    service.session.commit()
    return response


@router.put("/layers/{layer_id}", response_model=LayerOut)
def update_layer(layer_id: UUID, body: LayerIn, service: ServiceDep) -> LayerOut:
    response = LayerOut.model_validate(service.update_layer(layer_id, body.model_dump()))
    service.session.commit()
    return response


@router.delete("/layers/{layer_id}", status_code=204)
def delete_layer(layer_id: UUID, service: ServiceDep) -> Response:
    service.delete_layer(layer_id)
    service.session.commit()
    return Response(status_code=204)


@router.get("/domains", response_model=list[DomainOut])
def list_domains(service: ServiceDep) -> list[DomainOut]:
    return [DomainOut.model_validate(domain) for domain in service.list_domains()]


@router.post("/domains", response_model=DomainOut, status_code=201)
def create_domain(body: DomainIn, service: ServiceDep) -> DomainOut:
    response = DomainOut.model_validate(service.create_domain(body.model_dump()))
    service.session.commit()
    return response


@router.put("/domains/{domain_id}", response_model=DomainOut)
def update_domain(domain_id: UUID, body: DomainIn, service: ServiceDep) -> DomainOut:
    response = DomainOut.model_validate(service.update_domain(domain_id, body.model_dump()))
    service.session.commit()
    return response


@router.delete("/domains/{domain_id}", status_code=204)
def delete_domain(domain_id: UUID, service: ServiceDep) -> Response:
    service.delete_domain(domain_id)
    service.session.commit()
    return Response(status_code=204)


@router.put("/tables/{table_id}/layer", response_model=TableLayerOut)
def assign_layer(table_id: UUID, body: TableLayerIn, service: ServiceDep) -> TableLayerOut:
    response = TableLayerOut.model_validate(service.assign_layer(table_id, body.layer_id))
    service.session.commit()
    return response


@router.get("/connections/{connection_id}", response_model=BusinessModelOut)
def get_business_model(connection_id: UUID, service: ServiceDep) -> BusinessModelOut:
    return BusinessModelOut.model_validate(service.get_model(connection_id))


@router.put("/connections/{connection_id}/canvases/{view}", response_model=CanvasOut)
def save_canvas(
    connection_id: UUID, view: Literal["business", "lineage"], body: CanvasIn, service: ServiceDep
) -> CanvasOut:
    response = CanvasOut.model_validate(service.save_canvas(connection_id, view, body.layout))
    service.session.commit()
    return response


@router.put("/connections/{connection_id}/lineage-edges", response_model=EdgeOut)
def save_edge(connection_id: UUID, body: EdgeIn, service: ServiceDep) -> EdgeOut:
    response = EdgeOut.model_validate(service.save_edge(connection_id, body.model_dump()))
    service.session.commit()
    return response


@router.delete("/connections/{connection_id}/lineage-edges/{edge_id}", status_code=204)
def delete_edge(connection_id: UUID, edge_id: UUID, service: ServiceDep) -> Response:
    service.delete_edge(connection_id, edge_id)
    service.session.commit()
    return Response(status_code=204)
