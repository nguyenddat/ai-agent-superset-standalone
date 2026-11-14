from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from backend.core.setting import config

from ..dependencies import get_metric_service
from ..schemas.schema_metric import (
    LinkDatabaseIn,
    MetricIn,
    MetricOut,
    MetricPatch,
    SupersetDatabaseOut,
    SupersetUserOut,
    SyncOut,
)
from ..services import MetricService
from ..services.superset_client import SupersetClient
from ..utils.exceptions import SupersetNotConfiguredError

router = APIRouter(prefix="/api/v1/metrics", tags=["metric-management"])
ServiceDep = Annotated[MetricService, Depends(get_metric_service)]


@router.get("", response_model=list[MetricOut])
def list_metrics(
    service: ServiceDep, connection_id: UUID | None = None
) -> list[MetricOut]:
    return [
        MetricOut.model_validate(row) for row in service.list_metrics(connection_id)
    ]


@router.post("", response_model=MetricOut, status_code=201)
def create_metric(body: MetricIn, service: ServiceDep) -> MetricOut:
    response = MetricOut.model_validate(service.create_metric(body.model_dump()))
    service.session.commit()
    return response


@router.get("/superset/databases", response_model=list[SupersetDatabaseOut])
def list_superset_databases(service: ServiceDep) -> list[SupersetDatabaseOut]:
    return [SupersetDatabaseOut.model_validate(row) for row in service.list_databases()]


@router.get("/superset/users", response_model=list[SupersetUserOut])
def list_superset_users(service: ServiceDep) -> list[SupersetUserOut]:
    return [SupersetUserOut.model_validate(row) for row in service.list_users()]


@router.post("/superset/sync", response_model=SyncOut)
def sync_superset(service: ServiceDep) -> SyncOut:
    if (
        not config.superset_url
        or not config.superset_username
        or not config.superset_password
    ):
        raise SupersetNotConfiguredError()
    client = SupersetClient(
        config.superset_url,
        config.superset_username,
        config.superset_password.get_secret_value(),
    )
    snapshot = client.fetch_snapshot()
    response = SyncOut.model_validate(service.sync_superset(client.base_url, snapshot))
    service.session.commit()
    return response


@router.put(
    "/superset/databases/{database_id}/link", response_model=SupersetDatabaseOut
)
def link_superset_database(
    database_id: UUID, body: LinkDatabaseIn, service: ServiceDep
) -> SupersetDatabaseOut:
    response = SupersetDatabaseOut.model_validate(
        service.link_database(database_id, body.connection_id)
    )
    service.session.commit()
    return response


@router.get("/{metric_id}", response_model=MetricOut)
def get_metric(metric_id: UUID, service: ServiceDep) -> MetricOut:
    return MetricOut.model_validate(service.get_metric(metric_id))


@router.patch("/{metric_id}", response_model=MetricOut)
def update_metric(metric_id: UUID, body: MetricPatch, service: ServiceDep) -> MetricOut:
    response = MetricOut.model_validate(
        service.update_metric(metric_id, body.model_dump(exclude_unset=True))
    )
    service.session.commit()
    return response


@router.delete("/{metric_id}", status_code=204)
def delete_metric(metric_id: UUID, service: ServiceDep) -> Response:
    service.delete_metric(metric_id)
    service.session.commit()
    return Response(status_code=204)
