from fastapi import APIRouter

from app.domains.identity.dependencies import DbSession, Member
from app.integrations.provider_status import ProviderStatus, provider_status

router = APIRouter(prefix="/organizations/{organization_id}", tags=["providers"])


@router.get("/provider-status", response_model=ProviderStatus)
def read_provider_status(member: Member, db: DbSession) -> ProviderStatus:
    return provider_status(db, member.organization.id)
