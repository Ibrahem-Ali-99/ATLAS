from fastapi import APIRouter

from app.api.v1 import (
    agents,
    approvals,
    assistant,
    auth,
    automation,
    billing,
    calendar,
    campaigns,
    crm,
    demo,
    health,
    hooks,
    inbox,
    integrations,
    intelligence,
    invitations,
    knowledge,
    onboarding,
    organizations,
    providers,
    workflow_definitions,
)

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(demo.router)
router.include_router(organizations.router, tags=["organizations"])
router.include_router(providers.router)
router.include_router(crm.router)
router.include_router(knowledge.router)
router.include_router(assistant.router)
router.include_router(agents.router)
router.include_router(approvals.router)
router.include_router(automation.router)
router.include_router(billing.router)
router.include_router(calendar.router)
router.include_router(campaigns.router)
router.include_router(campaigns.preferences)
router.include_router(campaigns.feedback)
router.include_router(onboarding.router)
router.include_router(inbox.router)
router.include_router(inbox.public_widget_router)
router.include_router(workflow_definitions.router)
router.include_router(intelligence.router)
router.include_router(invitations.router)
router.include_router(integrations.router)
router.include_router(hooks.router)
