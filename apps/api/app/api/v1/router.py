from fastapi import APIRouter

from app.api.v1 import (
    agents,
    approvals,
    assistant,
    auth,
    automation,
    crm,
    health,
    hooks,
    integrations,
    intelligence,
    knowledge,
    organizations,
    providers,
)

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(organizations.router, tags=["organizations"])
router.include_router(providers.router)
router.include_router(crm.router)
router.include_router(knowledge.router)
router.include_router(assistant.router)
router.include_router(agents.router)
router.include_router(approvals.router)
router.include_router(automation.router)
router.include_router(intelligence.router)
router.include_router(integrations.router)
router.include_router(hooks.router)
