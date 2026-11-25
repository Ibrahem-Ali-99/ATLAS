import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.models import WorkflowDefinition
from app.domains.billing.service import enforce_limit
from app.domains.identity.dependencies import Admin, CsrfAdmin, DbSession

router = APIRouter(
    prefix="/organizations/{organization_id}/workflow-definitions", tags=["workflows"]
)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_TRIGGERS = {"lead_created", "lead_status_changed", "schedule"}
_ACTIONS = {"update_lead", "create_task", "prepare_follow_up"}


class WorkflowBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    definition: dict[str, Any]


def _validate(definition: dict[str, Any]) -> None:
    trigger = definition.get("trigger")
    actions = definition.get("actions")
    if (
        trigger not in _TRIGGERS
        or not isinstance(actions, list)
        or not actions
        or len(actions) > 20
    ):
        raise AppError(
            422,
            "invalid_workflow_definition",
            "A workflow needs one supported trigger and one to twenty actions",
        )
    for action in actions:
        if not isinstance(action, dict) or action.get("type") not in _ACTIONS:
            raise AppError(
                422, "invalid_workflow_definition", "The workflow contains an unsupported action"
            )
    if trigger == "schedule" and not isinstance(definition.get("schedule"), str):
        raise AppError(
            422, "invalid_workflow_definition", "Scheduled workflows require a schedule expression"
        )


def _out(row: WorkflowDefinition) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description,
        "version": row.version,
        "active": row.active,
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "definition": row.definition,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_definitions(admin: Admin, db: DbSession) -> list[dict[str, object]]:
    return [
        _out(row)
        for row in db.scalars(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.organization_id == admin.organization.id)
            .order_by(WorkflowDefinition.updated_at.desc())
        ).all()
    ]


@router.post("", status_code=201)
def create_definition(body: WorkflowBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    if not _SLUG.fullmatch(body.slug):
        raise AppError(422, "invalid_workflow_slug", "Use lowercase letters, numbers, and hyphens")
    _validate(body.definition)
    enforce_limit(db, admin.organization.id, "active_workflows")
    row = WorkflowDefinition(
        organization_id=admin.organization.id, created_by=admin.user.id, **body.model_dump()
    )
    if body.definition.get("trigger") == "schedule":
        row.next_run_at = datetime.now(UTC) + timedelta(
            seconds=max(60, int(body.definition.get("interval_seconds", 3600)))
        )
    db.add(row)
    record_event(
        db,
        admin.organization.id,
        "workflow_created",
        {"workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/{workflow_id}")
def update_definition(
    workflow_id: uuid.UUID, body: WorkflowBody, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    _validate(body.definition)
    row.name, row.slug, row.description, row.definition, row.version = (
        body.name,
        body.slug,
        body.description,
        body.definition,
        row.version + 1,
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{workflow_id}/activate")
def activate(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    row = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    _validate(row.definition)
    enforce_limit(db, admin.organization.id, "active_workflows")
    row.active = True
    if row.definition.get("trigger") == "schedule" and row.next_run_at is None:
        row.next_run_at = datetime.now(UTC) + timedelta(
            seconds=max(60, int(row.definition.get("interval_seconds", 3600)))
        )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{workflow_id}/pause")
def pause(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    row = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    row.active = False
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{workflow_id}/duplicate", status_code=201)
def duplicate(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    source = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
    )
    if source is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    enforce_limit(db, admin.organization.id, "active_workflows")
    row = WorkflowDefinition(
        organization_id=admin.organization.id,
        created_by=admin.user.id,
        name=f"Copy of {source.name}",
        slug=f"{source.slug}-copy-{str(uuid.uuid4())[:8]}",
        description=source.description,
        definition=source.definition,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{workflow_id}", status_code=204)
def delete(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> None:
    row = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    db.delete(row)
    db.commit()
