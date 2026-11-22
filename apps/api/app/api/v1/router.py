from fastapi import APIRouter

from app.api.v1 import auth, health, organizations

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(organizations.router, tags=["organizations"])
