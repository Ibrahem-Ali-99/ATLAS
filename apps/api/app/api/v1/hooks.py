from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.domains.automation import hooks
from app.domains.identity.dependencies import DbSession

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/lead-processed")
async def lead_processed(request: Request, db: DbSession) -> JSONResponse:
    code, body = hooks.accept_lead_processed(db, request.headers, await request.body())
    return JSONResponse(status_code=code, content=body)


@router.post("/follow-ups")
async def follow_ups(request: Request, db: DbSession) -> JSONResponse:
    code, body = hooks.accept_follow_ups(db, request.headers, await request.body())
    return JSONResponse(status_code=code, content=body)


@router.post("/follow-ups/request")
async def follow_up_request(request: Request, db: DbSession) -> JSONResponse:
    code, body = hooks.accept_follow_up_request(db, request.headers, await request.body())
    return JSONResponse(status_code=code, content=body)
