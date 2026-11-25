import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.approvals import service as approvals
from app.domains.approvals.schemas import ApprovalOut
from app.domains.automation import status
from app.domains.automation.hooks import create_webhook_key
from app.domains.automation.models import WorkflowTask
from app.domains.automation.schemas import (
    AutomationSnapshot,
    BookingOut,
    EmailActivityOut,
    WebhookKeyOut,
)
from app.domains.identity.dependencies import CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.identity.models import Membership, User
from app.domains.provenance.origin import DataScope
from app.integrations.calendar import calendar_adapter

router = APIRouter(prefix="/organizations/{organization_id}", tags=["automation"])


class TaskStatusBody(BaseModel):
    status: str = Field(pattern=r"^(open|in_progress|completed)$")
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")


@router.get("/workflow-tasks")
def workflow_tasks(
    member: Member,
    db: DbSession,
    status_filter: str | None = None,
    assignee_user_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
) -> list[dict[str, object]]:
    query = select(WorkflowTask).where(WorkflowTask.organization_id == member.organization.id)
    if status_filter:
        query = query.where(WorkflowTask.status == status_filter)
    if assignee_user_id:
        query = query.where(WorkflowTask.assignee_user_id == assignee_user_id)
    if opportunity_id:
        query = query.where(WorkflowTask.opportunity_id == opportunity_id)
    return [
        {
            "id": task.id,
            "workflow_run_id": task.workflow_run_id,
            "lead_id": task.lead_id,
            "contact_id": task.contact_id,
            "opportunity_id": task.opportunity_id,
            "assignee_user_id": task.assignee_user_id,
            "title": task.title,
            "description": task.description,
            "due_at": task.due_at,
            "status": task.status,
            "priority": task.priority,
            "source": task.source,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        for task in db.scalars(query.order_by(WorkflowTask.created_at.desc())).all()
    ]


@router.post("/workflow-tasks", status_code=201)
def create_workflow_task(
    body: TaskCreateBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    from app.domains.crm.models import Contact, Lead, Opportunity

    for model, value in (
        (Lead, body.lead_id),
        (Contact, body.contact_id),
        (Opportunity, body.opportunity_id),
    ):
        if (
            value is not None
            and db.scalar(
                select(model).where(
                    model.id == value, model.organization_id == member.organization.id
                )
            )
            is None
        ):
            raise AppError(404, "related_record_not_found", "Related record not found")
    if body.assignee_user_id is not None:
        if (
            db.scalar(
                select(Membership)
                .join(Membership.user)
                .where(
                    Membership.organization_id == member.organization.id,
                    Membership.user_id == body.assignee_user_id,
                    User.is_active.is_(True),
                )
            )
            is None
        ):
            raise AppError(
                404, "assignee_not_found", "Assignee is not an active organization member"
            )
    task = WorkflowTask(
        organization_id=member.organization.id,
        title=body.title,
        description=body.description,
        lead_id=body.lead_id,
        contact_id=body.contact_id,
        opportunity_id=body.opportunity_id,
        assignee_user_id=body.assignee_user_id or member.user.id,
        due_at=body.due_at,
        priority=body.priority,
        source="manual",
    )
    db.add(task)
    db.commit()
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "source": task.source,
    }


@router.patch("/workflow-tasks/{task_id}")
def update_workflow_task(
    task_id: uuid.UUID, body: TaskStatusBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    task = db.scalar(
        select(WorkflowTask).where(
            WorkflowTask.id == task_id, WorkflowTask.organization_id == member.organization.id
        )
    )
    if task is None:
        raise AppError(404, "task_not_found", "Task not found")
    task.status = body.status
    if body.priority is not None:
        task.priority = body.priority
    if body.assignee_user_id is not None:
        task.assignee_user_id = body.assignee_user_id
    db.commit()
    return {"id": task.id, "status": task.status}


@router.get("/automations", response_model=AutomationSnapshot)
def get_automations(
    member: Member, db: DbSession, scope: DataScope = DataScope.operational
) -> AutomationSnapshot:
    return AutomationSnapshot.model_validate(status.snapshot(db, member.organization.id, scope))


@router.get("/email-activity", response_model=list[EmailActivityOut])
def get_email_activity(
    member: Member, db: DbSession, scope: DataScope = DataScope.operational
) -> list[EmailActivityOut]:
    return [
        EmailActivityOut.model_validate(item)
        for item in status._email_activity(db, member.organization.id, scope)
    ]


@router.post("/integrations/webhook-keys", response_model=WebhookKeyOut, status_code=201)
def create_key(member: CsrfAdmin, db: DbSession) -> WebhookKeyOut:
    key, secret = create_webhook_key(db, member.organization.id)
    return WebhookKeyOut(id=key.id, name=key.name, secret=secret)


@router.post("/approvals/{approval_id}/execute", response_model=ApprovalOut)
def execute_approval(approval_id: uuid.UUID, member: CsrfAdmin, db: DbSession) -> ApprovalOut:
    approvals.execute_approved(db, member.organization.id, approval_id)
    approval = approvals.get_approval(db, member.organization.id, approval_id)
    return ApprovalOut.model_validate(approval)


@router.post("/calendar/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: uuid.UUID, member: CsrfAdmin, db: DbSession) -> BookingOut:
    booking = calendar_adapter().cancel(db, member.organization.id, booking_id)
    return BookingOut(
        id=booking.id,
        lead_id=booking.lead_id,
        status=booking.status.value,
        provider=booking.provider,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        provider_event_id=booking.provider_event_id,
    )
