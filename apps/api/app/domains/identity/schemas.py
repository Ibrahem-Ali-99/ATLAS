import uuid
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


class OrganizationAccessResponse(BaseModel):
    organization_id: uuid.UUID
    role: MembershipRole
    access: Literal["member", "admin"]


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
