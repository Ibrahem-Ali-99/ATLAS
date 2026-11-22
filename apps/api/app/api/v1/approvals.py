import uuid

from fastapi import APIRouter, Query

from app.domains.approvals import service
from app.domains.approvals.models import ApprovalStatus
from app.domains.approvals.schemas import ApprovalOut, ApprovalPage, DecisionIn
from app.domains.identity.dependencies import CsrfAdmin, DbSession, Member

router = APIRouter(prefix="/organizations/{organization_id}", tags=["approvals"])


@router.get("/approvals", response_model=ApprovalPage)
def list_approvals(
    member: Member,
    db: DbSession,
    status: ApprovalStatus | None = None,
    run_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApprovalPage:
    items, total = service.list_approvals(
        db,
        member.organization.id,
        status=status,
        run_id=run_id,
        page=page,
        page_size=page_size,
    )
    return ApprovalPage(
        page=page,
        page_size=page_size,
        total=total,
        items=[ApprovalOut.model_validate(item) for item in items],
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: uuid.UUID, member: Member, db: DbSession) -> ApprovalOut:
    approval = service.get_approval(db, member.organization.id, approval_id)
    return ApprovalOut.model_validate(approval)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
def approve(
    approval_id: uuid.UUID,
    member: CsrfAdmin,
    db: DbSession,
    body: DecisionIn | None = None,
) -> ApprovalOut:
    approval = service.decide(
        db,
        member.organization.id,
        approval_id,
        member.user.id,
        approved=True,
        note=None if body is None else body.note,
    )
    return ApprovalOut.model_validate(approval)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
def reject(
    approval_id: uuid.UUID,
    member: CsrfAdmin,
    db: DbSession,
    body: DecisionIn | None = None,
) -> ApprovalOut:
    approval = service.decide(
        db,
        member.organization.id,
        approval_id,
        member.user.id,
        approved=False,
        note=None if body is None else body.note,
    )
    return ApprovalOut.model_validate(approval)
