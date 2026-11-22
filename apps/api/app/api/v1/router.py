from fastapi import APIRouter

from app.api.v1 import assistant, auth, crm, health, knowledge, organizations

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(organizations.router, tags=["organizations"])
router.include_router(crm.router)
router.include_router(knowledge.router)
router.include_router(assistant.router)
