from fastapi import APIRouter

from app.domains.identity.dependencies import Admin, CurrentUser, DbSession, Member
from app.domains.identity.schemas import (
    OrganizationAccessResponse,
    OrganizationListResponse,
    OrganizationOut,
    organization_out,
)
from app.domains.identity.service import list_memberships

router = APIRouter(prefix="/organizations")


@router.get("", response_model=OrganizationListResponse)
def list_organizations(user: CurrentUser, db: DbSession) -> OrganizationListResponse:
    organizations = [
        organization_out(organization, membership.role)
        for organization, membership in list_memberships(db, user.id)
    ]
    return OrganizationListResponse(organizations=organizations)


@router.get("/{organization_id}", response_model=OrganizationOut)
def get_organization(context: Member) -> OrganizationOut:
    return organization_out(context.organization, context.membership.role)


@router.get("/{organization_id}/workspace", response_model=OrganizationAccessResponse)
def workspace(context: Member) -> OrganizationAccessResponse:
    return OrganizationAccessResponse(
        organization_id=context.organization.id,
        role=context.membership.role,
        access="member",
    )


@router.get("/{organization_id}/admin", response_model=OrganizationAccessResponse)
def admin_access(context: Admin) -> OrganizationAccessResponse:
    return OrganizationAccessResponse(
        organization_id=context.organization.id,
        role=context.membership.role,
        access="admin",
    )
