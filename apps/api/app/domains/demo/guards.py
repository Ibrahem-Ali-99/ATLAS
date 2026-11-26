"""Refuse credential and billing routes for a demonstration organization."""

from app.core.errors import AppError
from app.domains.demo.access import is_visitor_slug
from app.domains.identity.dependencies import Admin
from app.domains.identity.models import Organization

DEMO_CONFIGURATION_MESSAGE = (
    "Demo sessions cannot open credentials, billing, invitations, or live provider actions."
)


def refuse_visitor_organization(organization: Organization) -> None:
    if is_visitor_slug(organization.slug):
        raise AppError(403, "demo_restricted", DEMO_CONFIGURATION_MESSAGE)


def refuse_visitor_configuration(admin: Admin) -> None:
    refuse_visitor_organization(admin.organization)
