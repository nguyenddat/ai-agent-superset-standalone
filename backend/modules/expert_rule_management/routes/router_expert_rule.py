from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_expert_rule_service
from ..schemas.schema_expert_rule import DiscoveryRule, ReviewIn, RevisionOut, RuleCreate, RuleOut, RuleUpdate
from ..services import ExpertRuleService

router = APIRouter(prefix="/api/v1/expert-rules", tags=["expert-rule-management"])
ServiceDep = Annotated[ExpertRuleService, Depends(get_expert_rule_service)]


@router.get("", response_model=list[RuleOut])
def list_rules(connection_id: UUID, service: ServiceDep) -> list[dict[str, Any]]:
    return service.list_rules(connection_id)


@router.get("/options")
def rule_options(connection_id: UUID, service: ServiceDep) -> dict[str, Any]:
    return {"tables": service.options(connection_id)}


@router.get("/discovery", response_model=dict[str, list[DiscoveryRule]])
def discover_rules(connection_id: UUID, service: ServiceDep) -> dict[str, Any]:
    return {"rules": service.discovery(connection_id)}


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(body: RuleCreate, service: ServiceDep) -> dict[str, Any]:
    result = service.create_rule(body.model_dump())
    service.session.commit()
    return result


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(rule_id: UUID, service: ServiceDep) -> dict[str, Any]:
    return service.get_rule(rule_id)


@router.get("/{rule_id}/revisions", response_model=list[RevisionOut])
def list_revisions(rule_id: UUID, service: ServiceDep) -> list[dict[str, Any]]:
    return service.list_revisions(rule_id)


@router.put("/{rule_id}/draft", response_model=RuleOut)
def update_rule(rule_id: UUID, body: RuleUpdate, service: ServiceDep) -> dict[str, Any]:
    result = service.update_rule(rule_id, body.model_dump())
    service.session.commit()
    return result


@router.post("/{rule_id}/approve", response_model=RuleOut)
def approve_rule(rule_id: UUID, body: ReviewIn, service: ServiceDep) -> dict[str, Any]:
    result = service.approve(rule_id, body.expected_revision)
    service.session.commit()
    return result


@router.post("/{rule_id}/revoke", response_model=RuleOut)
def revoke_rule(rule_id: UUID, body: ReviewIn, service: ServiceDep) -> dict[str, Any]:
    result = service.revoke(rule_id, body.expected_revision)
    service.session.commit()
    return result


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID, service: ServiceDep) -> Response:
    service.delete_rule(rule_id)
    service.session.commit()
    return Response(status_code=204)
