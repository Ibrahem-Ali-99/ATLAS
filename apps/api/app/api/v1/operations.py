"""Operator controls for the public assistant. Visitors cannot change them."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.domains.assistant.public_budget import (
    public_inference_killed,
    set_public_inference_killed,
)
from app.domains.demo.guards import refuse_visitor_organization
from app.domains.identity.dependencies import Admin, CsrfAdmin, DbSession

router = APIRouter(prefix="/organizations/{organization_id}", tags=["operations"])


class PublicInferenceSwitch(BaseModel):
    killed: bool


class PublicInferenceStatus(BaseModel):
    enabled: bool
    authorized: bool
    killed: bool


@router.get("/public-inference", response_model=PublicInferenceStatus)
def read_public_inference(admin: Admin, db: DbSession) -> PublicInferenceStatus:
    refuse_visitor_organization(admin.organization)
    settings = get_settings()
    return PublicInferenceStatus(
        enabled=settings.public_inference_enabled,
        authorized=settings.public_llm_authorized,
        killed=public_inference_killed(db),
    )


@router.post("/public-inference", response_model=PublicInferenceStatus)
def update_public_inference(
    body: PublicInferenceSwitch, admin: CsrfAdmin, db: DbSession
) -> PublicInferenceStatus:
    refuse_visitor_organization(admin.organization)
    killed = set_public_inference_killed(db, body.killed)
    settings = get_settings()
    return PublicInferenceStatus(
        enabled=settings.public_inference_enabled,
        authorized=settings.public_llm_authorized,
        killed=killed,
    )
