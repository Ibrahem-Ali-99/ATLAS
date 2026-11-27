import uuid

from fastapi import APIRouter

from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.identity.dependencies import (
    Admin,
    CsrfAdmin,
    CsrfMember,
    CurrentUser,
    DbSession,
    Member,
)
from app.domains.identity.models import User
from app.domains.identity.schemas import (
    OrganizationAccessResponse,
    OrganizationListResponse,
    OrganizationOut,
    OrganizationUpdate,
    RoleUpdate,
    TeamMemberOut,
    organization_out,
)
from app.domains.identity.service import (
    list_memberships,
    list_team,
    leave_organization,
    remove_membership,
    update_membership_role,
)

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


@router.patch("/{organization_id}", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate, admin: CsrfAdmin, db: DbSession
) -> OrganizationOut:
    admin.organization.name = body.name.strip()
    record_event(
        db,
        admin.organization.id,
        "organization_updated",
        {"fields": ["name"]},
        actor_id=admin.user.id,
    )
    db.commit()
    return organization_out(admin.organization, admin.membership.role)


@router.get("/{organization_id}/members", response_model=list[TeamMemberOut])
def members(admin: Member, db: DbSession) -> list[TeamMemberOut]:
    return [
        TeamMemberOut(
            membership_id=m.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            joined_at=m.created_at,
            is_active=u.is_active,
        )
        for m, u in list_team(db, admin.organization.id)
    ]


@router.patch("/{organization_id}/members/{membership_id}", response_model=TeamMemberOut)
def change_role(
    membership_id: uuid.UUID, body: RoleUpdate, admin: CsrfAdmin, db: DbSession
) -> TeamMemberOut:
    member = update_membership_role(db, admin.organization.id, membership_id, body.role)
    user = db.get(User, member.user_id)
    if user is None:
        raise AppError(404, "member_not_found", "Member not found")
    record_event(
        db,
        admin.organization.id,
        "membership_role_changed",
        {"membership_id": str(member.id), "role": body.role.value},
        actor_id=admin.user.id,
    )
    db.commit()
    return TeamMemberOut(
        membership_id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.created_at,
        is_active=user.is_active,
    )


@router.delete("/{organization_id}/members/{membership_id}", status_code=204)
def remove_member(membership_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> None:
    remove_membership(db, admin.organization.id, membership_id)
    record_event(
        db,
        admin.organization.id,
        "membership_removed",
        {"membership_id": str(membership_id)},
        actor_id=admin.user.id,
    )
    db.commit()


@router.post("/{organization_id}/leave", status_code=204)
def leave(member: CsrfMember, db: DbSession) -> None:
    leave_organization(db, member.organization.id, member.user.id)
    record_event(
        db,
        member.organization.id,
        "membership_left",
        {"membership_id": str(member.membership.id)},
        actor_id=member.user.id,
    )
    db.commit()
