from fastapi import APIRouter
from sqlalchemy import select

from app.domains.billing.service import enforce_limit
from app.domains.identity.dependencies import Admin, CsrfAdmin, DbSession
from app.domains.identity.invitation_models import OrganizationInvitation
from app.domains.identity.invitation_service import accept_invitation, create_invitation
from app.domains.identity.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationCreated,
    InvitationStatusOut,
    user_out,
)

router = APIRouter(tags=["identity"])


@router.get(
    "/organizations/{organization_id}/invitations", response_model=list[InvitationStatusOut]
)
def list_pending(admin: Admin, db: DbSession) -> list[InvitationStatusOut]:
    rows = db.scalars(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == admin.organization.id)
        .order_by(OrganizationInvitation.created_at.desc())
    ).all()
    return [InvitationStatusOut.model_validate(row) for row in rows]


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InvitationCreated,
    status_code=201,
)
def create(body: InvitationCreate, admin: CsrfAdmin, db: DbSession) -> InvitationCreated:
    enforce_limit(db, admin.organization.id, "seats")
    invitation, token = create_invitation(db, admin.organization.id, admin.user.id, str(body.email))
    return InvitationCreated(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role.value,
        expires_at=invitation.expires_at,
        token=token,
    )


@router.post("/invitations/accept", response_model=dict[str, object], status_code=201)
def accept(body: InvitationAccept, db: DbSession) -> dict[str, object]:
    user, organization = accept_invitation(
        db, body.token, full_name=body.full_name, password=body.password
    )
    return {
        "user": user_out(user),
        "organization_id": organization.id,
        "organization_name": organization.name,
    }
