import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.identity.models import MembershipRole, Organization, User


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str


class MembershipOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    role: MembershipRole


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: MembershipRole


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationOut]


class AuthResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    csrf_token: str
    demo: bool = False
    demo_expires_at: datetime | None = None


class OrganizationAccessResponse(BaseModel):
    organization_id: uuid.UUID
    role: MembershipRole
    access: Literal["member", "admin"]


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamMemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: MembershipRole
    joined_at: datetime
    is_active: bool


class RoleUpdate(BaseModel):
    role: MembershipRole


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class InvitationCreate(BaseModel):
    email: EmailStr


class InvitationCreated(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Literal["staff"]
    expires_at: datetime
    token: str


class InvitationStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: Literal["staff"]
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["atlas-api"]


class ReadyResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


def membership_out(
    organization: Organization, role: MembershipRole, membership_id: uuid.UUID
) -> MembershipOut:
    return MembershipOut(
        id=membership_id,
        organization_id=organization.id,
        organization_name=organization.name,
        organization_slug=organization.slug,
        role=role,
    )


def organization_out(organization: Organization, role: MembershipRole) -> OrganizationOut:
    return OrganizationOut(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        role=role,
    )


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name)
