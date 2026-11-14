from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_glossary_service
from ..schemas.schema_glossary import GlossaryCreate, GlossaryOut, GlossaryUpdate, ReviewIn, RevisionOut
from ..services import GlossaryService

router = APIRouter(prefix="/api/v1/glossary", tags=["glossary-management"])
ServiceDep = Annotated[GlossaryService, Depends(get_glossary_service)]


@router.get("", response_model=list[GlossaryOut])
def list_terms(connection_id: UUID, service: ServiceDep) -> list[dict[str, Any]]:
    return service.list_terms(connection_id)


@router.get("/discovery")
def discover_terms(connection_id: UUID, service: ServiceDep) -> dict[str, Any]:
    return {"terms": service.discovery(connection_id)}


@router.post("", response_model=GlossaryOut, status_code=201)
def create_term(body: GlossaryCreate, service: ServiceDep) -> dict[str, Any]:
    result = service.create_term(body.model_dump())
    service.session.commit()
    return result


@router.get("/{term_id}", response_model=GlossaryOut)
def get_term(term_id: UUID, service: ServiceDep) -> dict[str, Any]:
    return service.get_term(term_id)


@router.get("/{term_id}/revisions", response_model=list[RevisionOut])
def list_revisions(term_id: UUID, service: ServiceDep) -> list[dict[str, Any]]:
    return service.list_revisions(term_id)


@router.put("/{term_id}/draft", response_model=GlossaryOut)
def update_term(term_id: UUID, body: GlossaryUpdate, service: ServiceDep) -> dict[str, Any]:
    result = service.update_term(term_id, body.model_dump())
    service.session.commit()
    return result


@router.post("/{term_id}/approve", response_model=GlossaryOut)
def approve_term(term_id: UUID, body: ReviewIn, service: ServiceDep) -> dict[str, Any]:
    result = service.approve(term_id, body.expected_revision)
    service.session.commit()
    return result


@router.post("/{term_id}/revoke", response_model=GlossaryOut)
def revoke_term(term_id: UUID, body: ReviewIn, service: ServiceDep) -> dict[str, Any]:
    result = service.revoke(term_id, body.expected_revision)
    service.session.commit()
    return result


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: UUID, service: ServiceDep) -> Response:
    service.delete_term(term_id)
    service.session.commit()
    return Response(status_code=204)
