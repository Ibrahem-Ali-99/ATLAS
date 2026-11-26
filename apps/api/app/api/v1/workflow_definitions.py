import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.models import (
    WorkflowDefinition,
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.billing.service import enforce_limit, enforce_workflow_definition_limit
from app.domains.crm.models import Lead, LeadStatus, Opportunity, PipelineStage
from app.domains.identity.dependencies import Admin, CsrfAdmin, DbSession
from app.domains.provenance.origin import Origin

router = APIRouter(
    prefix="/organizations/{organization_id}/workflow-definitions", tags=["workflows"]
)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_TRIGGERS = {
    "lead_created",
    "lead_status_changed",
    "opportunity_stage_changed",
    "schedule",
    "manual",
}
_LEAD_TRIGGERS = {"lead_created", "lead_status_changed"}
_ACTIONS = {"update_lead", "create_task", "prepare_follow_up", "require_approval"}
_LEAD_STATUSES = {item.value for item in LeadStatus}


class WorkflowBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    definition: dict[str, Any]
    expected_version: int | None = Field(default=None, ge=1)


def _validate(definition: dict[str, Any]) -> None:
    trigger = definition.get("trigger")
    actions = definition.get("actions")
    if (
        not isinstance(trigger, str)
        or trigger not in _TRIGGERS
        or not isinstance(actions, list)
        or not actions
        or len(actions) > 20
    ):
        raise AppError(
            422,
            "invalid_workflow_definition",
            "A workflow needs one supported trigger and one to twenty actions",
        )
    conditions = definition.get("conditions", [])
    field = (
        "lead_status"
        if trigger in _LEAD_TRIGGERS
        else ("opportunity_stage" if trigger == "opportunity_stage_changed" else None)
    )
    if not isinstance(conditions, list) or len(conditions) > 5:
        raise AppError(422, "invalid_workflow_definition", "Add up to five conditions")
    if definition.get("condition_mode", "all") not in ("all", "any"):
        raise AppError(422, "invalid_workflow_definition", "Choose how to match conditions")
    otherwise = definition.get("otherwise_actions", [])
    if not isinstance(otherwise, list) or len(actions) + len(otherwise) > 20:
        raise AppError(
            422, "invalid_workflow_definition", "Use up to twenty steps across both paths"
        )
    if otherwise and not conditions:
        raise AppError(
            422, "invalid_workflow_definition", "Add a condition to use an otherwise path"
        )
    for condition in conditions:
        if (
            not isinstance(condition, dict)
            or field is None
            or condition.get("field") != field
            or condition.get("operator") not in ("equals", "not_equals")
            or not isinstance(condition.get("value"), str)
            or not _SLUG.fullmatch(condition["value"])
            or (field == "lead_status" and condition["value"] not in _LEAD_STATUSES)
        ):
            raise AppError(
                422, "invalid_workflow_definition", "Choose a condition supported by the trigger"
            )
    _validate_actions(actions, trigger)
    if otherwise:
        _validate_actions(otherwise, trigger)
    interval = definition.get("interval_seconds", 3600)
    if trigger == "schedule" and (type(interval) is not int or not 60 <= interval <= 31_536_000):
        raise AppError(
            422,
            "invalid_workflow_definition",
            "Choose a repeat interval from one minute to one year",
        )


def _validate_actions(actions: list[Any], trigger: str) -> None:
    if not any(
        isinstance(action, dict) and action.get("type") != "require_approval" for action in actions
    ):
        raise AppError(422, "invalid_workflow_definition", "Add an action after the approval step")
    for index, action in enumerate(actions):
        kind = action.get("type") if isinstance(action, dict) else None
        if not isinstance(kind, str) or kind not in _ACTIONS:
            raise AppError(
                422, "invalid_workflow_definition", "The workflow contains an unsupported action"
            )
        if kind in {"update_lead", "prepare_follow_up"} and trigger not in _LEAD_TRIGGERS:
            raise AppError(
                422, "invalid_workflow_definition", "This action requires a lead trigger"
            )
        if kind == "update_lead":
            status = action.get("status")
            if not isinstance(status, str) or status not in _LEAD_STATUSES:
                raise AppError(422, "invalid_workflow_definition", "Choose a valid lead status")
        if kind == "create_task":
            title = action.get("title", "Workflow follow-up")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                raise AppError(
                    422, "invalid_workflow_definition", "Enter a task title up to 200 characters"
                )
            priority = action.get("priority", "normal")
            due = action.get("due_in_hours")
            description = action.get("description", "")
            if (
                priority not in ("low", "normal", "high", "urgent")
                or (due is not None and (type(due) is not int or not 1 <= due <= 8760))
                or not isinstance(description, str)
                or len(description) > 2000
            ):
                raise AppError(
                    422,
                    "invalid_workflow_definition",
                    "Check the task priority, due time and description",
                )
        if kind == "require_approval":
            note = action.get("note", "")
            if index != 0 or not isinstance(note, str) or len(note) > 500:
                raise AppError(
                    422, "invalid_workflow_definition", "Place one approval before all actions"
                )
    if sum(action["type"] == "prepare_follow_up" for action in actions) > 1:
        raise AppError(422, "invalid_workflow_definition", "Use one follow-up draft per path")


def _out(row: WorkflowDefinition) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description,
        "version": row.version,
        "active": row.active,
        "activated_at": row.activated_at,
        "archived_at": row.archived_at,
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "definition": row.definition,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _flush_definition(db: DbSession) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) != (
            "uq_workflow_definitions_org_slug"
        ):
            raise
        raise AppError(409, "workflow_name_conflict", "Use a different workflow name") from exc


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
    _validate_workspace(body.definition, admin, db)
    row = WorkflowDefinition(
        organization_id=admin.organization.id,
        created_by=admin.user.id,
        **body.model_dump(exclude={"expected_version"}),
    )
    db.add(row)
    _flush_definition(db)
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
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
        .with_for_update()
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    if row.active:
        raise AppError(409, "workflow_active", "Pause this workflow before editing it")
    if row.archived_at is not None:
        raise AppError(409, "workflow_archived", "Duplicate this archived workflow to edit a copy")
    if body.expected_version is not None and row.version != body.expected_version:
        raise AppError(
            409, "workflow_version_conflict", "This workflow changed. Reload before saving"
        )
    if not _SLUG.fullmatch(body.slug):
        raise AppError(422, "invalid_workflow_slug", "Use lowercase letters, numbers, and hyphens")
    _validate_workspace(body.definition, admin, db)
    row.name, row.slug, row.description, row.definition, row.version = (
        body.name,
        body.slug,
        body.description,
        body.definition,
        row.version + 1,
    )
    row.next_run_at = None
    _flush_definition(db)
    record_event(
        db,
        admin.organization.id,
        "workflow_updated",
        {"workflow_id": str(row.id), "version": row.version},
        actor_id=admin.user.id,
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{workflow_id}/activate")
def activate(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    row = db.scalar(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
        .with_for_update()
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    if row.active:
        return _out(row)
    if row.archived_at is not None:
        raise AppError(409, "workflow_archived", "Archived workflows cannot be activated")
    _validate_workspace(row.definition, admin, db)
    enforce_workflow_definition_limit(db, admin.organization.id)
    row.active = True
    row.activated_at = datetime.now(UTC)
    if row.definition.get("trigger") == "schedule":
        row.next_run_at = datetime.now(UTC) + timedelta(
            seconds=max(60, int(row.definition.get("interval_seconds", 3600)))
        )
    record_event(
        db,
        admin.organization.id,
        "workflow_activated",
        {"workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{workflow_id}/pause")
def pause(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    row = db.scalar(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.organization_id == admin.organization.id,
        )
        .with_for_update()
    )
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    if not row.active:
        return _out(row)
    row.active = False
    row.next_run_at = None
    record_event(
        db,
        admin.organization.id,
        "workflow_paused",
        {"workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
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
    row = WorkflowDefinition(
        organization_id=admin.organization.id,
        created_by=admin.user.id,
        name=f"Copy of {source.name}"[:120],
        slug=f"{source.slug[:66]}-copy-{uuid.uuid4().hex[:8]}",
        description=source.description,
        definition=source.definition,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


def _get_definition(
    workflow_id: uuid.UUID, admin: Admin, db: DbSession, *, lock: bool = False
) -> WorkflowDefinition:
    query = select(WorkflowDefinition).where(
        WorkflowDefinition.id == workflow_id,
        WorkflowDefinition.organization_id == admin.organization.id,
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise AppError(404, "workflow_not_found", "Workflow not found")
    return row


@router.delete("/{workflow_id}", status_code=204)
def archive(workflow_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> None:
    row = _get_definition(workflow_id, admin, db, lock=True)
    if row.archived_at is not None:
        return
    row.archived_at = datetime.now(UTC)
    row.active = False
    row.next_run_at = None
    record_event(
        db,
        admin.organization.id,
        "workflow_archived",
        {"workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
    db.commit()


@router.post("/validate")
def validate(body: WorkflowBody, admin: CsrfAdmin, db: DbSession) -> dict[str, bool]:
    _validate_workspace(body.definition, admin, db)
    return {"valid": True}


def _validate_workspace(definition: dict[str, Any], admin: Admin, db: DbSession) -> None:
    _validate(definition)
    for condition in definition.get("conditions", []):
        if condition["field"] == "opportunity_stage" and not db.scalar(
            select(PipelineStage.id).where(
                PipelineStage.organization_id == admin.organization.id,
                PipelineStage.key == condition["value"],
                PipelineStage.active.is_(True),
            )
        ):
            raise AppError(422, "invalid_workflow_definition", "Choose an active opportunity stage")


class ManualRun(BaseModel):
    request_id: uuid.UUID
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    dry_run: bool = False
    confirm_repeat: bool = False


_CONSEQUENTIAL = {"update_lead", "prepare_follow_up", "create_task"}


def _targets_record(run: WorkflowRun, body: ManualRun) -> bool:
    opportunity_id = str(body.opportunity_id) if body.opportunity_id else None
    if body.lead_id is not None and run.lead_id != body.lead_id:
        return False
    if opportunity_id is not None and run.payload.get("opportunity_id") != opportunity_id:
        return False
    if body.lead_id is None and opportunity_id is None and run.lead_id is not None:
        return False
    return True


def _run_in_progress(db: DbSession, row: WorkflowDefinition, body: ManualRun) -> bool:
    runs = db.scalars(_run_query(row).order_by(WorkflowRun.created_at.desc()).limit(40)).all()
    for run in runs:
        if run.payload.get("dry_run") or not _targets_record(run, body):
            continue
        if run.status in {WorkflowStatus.pending, WorkflowStatus.dispatching}:
            return True
        if (
            run.status == WorkflowStatus.accepted
            and run.payload.get("outcome") == "awaiting_approval"
        ):
            return True
    return False


def _effect_recorded(db: DbSession, row: WorkflowDefinition, body: ManualRun) -> bool:
    runs = db.scalars(_run_query(row).order_by(WorkflowRun.created_at.desc()).limit(40)).all()
    for run in runs:
        if run.payload.get("dry_run") or not _targets_record(run, body):
            continue
        steps = run.payload.get("steps") or []
        if any(
            isinstance(step, dict)
            and step.get("type") in _CONSEQUENTIAL
            and step.get("status") == "completed"
            for step in steps
        ):
            return True
    return False


def _run_out(run: WorkflowRun) -> dict[str, object]:
    return {
        "id": run.id,
        "status": run.payload.get("outcome", run.status.value),
        "manual": run.payload.get("manual", False),
        "dry_run": bool(run.payload.get("dry_run")),
        "branch": run.payload.get("branch"),
        "lead_id": run.lead_id,
        "opportunity_id": run.payload.get("opportunity_id"),
        "error": run.last_error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "steps": run.payload.get("steps", []),
        "review": run.payload.get("review"),
        "review_note": run.payload.get("review_note"),
        "approval_id": run.payload.get("approval_id"),
    }


def _run_query(row: WorkflowDefinition) -> Any:
    return select(WorkflowRun).where(
        WorkflowRun.organization_id == row.organization_id,
        WorkflowRun.payload["workflow_definition_id"].astext == str(row.id),
    )


@router.get("/{workflow_id}/runs")
def history(
    workflow_id: uuid.UUID, admin: Admin, db: DbSession, include: uuid.UUID | None = None
) -> list[dict[str, object]]:
    row = _get_definition(workflow_id, admin, db)
    query = _run_query(row)
    runs = list(db.scalars(query.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id).limit(50)))
    if include is not None and all(run.id != include for run in runs):
        included = db.scalar(query.where(WorkflowRun.id == include))
        if included is not None:
            runs.append(included)
    return [_run_out(run) for run in runs]


@router.get("/reviews")
def pending_reviews(admin: Admin, db: DbSession) -> list[dict[str, object]]:
    organization_id = admin.organization.id
    rows = db.execute(
        select(WorkflowRun, WorkflowDefinition)
        .join(
            WorkflowDefinition,
            cast(WorkflowDefinition.id, String)
            == WorkflowRun.payload["workflow_definition_id"].astext,
        )
        .where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.status == WorkflowStatus.accepted,
            WorkflowRun.payload["outcome"].astext == "awaiting_approval",
        )
        .order_by(WorkflowRun.created_at, WorkflowRun.id)
        .limit(50)
    )
    return [
        {
            "id": run.id,
            "workflow_id": definition.id,
            "name": definition.name,
            "note": run.payload.get("review_note"),
            "archived": definition.archived_at is not None,
        }
        for run, definition in rows
    ]


@router.post("/{workflow_id}/runs", status_code=202)
def manual_run(
    workflow_id: uuid.UUID, body: ManualRun, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = _get_definition(workflow_id, admin, db, lock=True)
    mode = "preview" if body.dry_run else "apply"
    key = hashlib.sha256(f"manual:{row.id}:{body.request_id}:{mode}".encode()).hexdigest()
    existing = db.scalar(_run_query(row).where(WorkflowRun.idempotency_key == key))
    if existing is not None:
        opportunity_id = str(body.opportunity_id) if body.opportunity_id else None
        if (
            existing.lead_id != body.lead_id
            or existing.payload.get("opportunity_id") != opportunity_id
        ):
            raise AppError(
                409, "workflow_request_conflict", "Use a new request for a different record"
            )
        return _run_out(existing)
    if row.archived_at is not None:
        raise AppError(409, "workflow_archived", "Archived workflows cannot run")
    if not body.dry_run and _run_in_progress(db, row, body):
        raise AppError(
            409,
            "workflow_run_in_progress",
            "This workflow is already running on this record. "
            "Wait until it finishes before running it again.",
        )
    if not body.dry_run and not body.confirm_repeat and _effect_recorded(db, row, body):
        raise AppError(
            409,
            "workflow_effect_already_recorded",
            "This workflow already changed this record. Confirm to run the actions again.",
        )
    _validate_workspace(row.definition, admin, db)
    trigger = row.definition["trigger"]
    if (trigger in _LEAD_TRIGGERS) != bool(body.lead_id) or (
        trigger == "opportunity_stage_changed"
    ) != bool(body.opportunity_id):
        raise AppError(
            422, "workflow_context_required", "Select the CRM record required by this trigger"
        )
    payload = {
        "workflow_definition_id": str(row.id),
        "definition": row.definition,
        "manual": True,
        "dry_run": body.dry_run,
    }
    origin = Origin.operational
    if body.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == body.lead_id,
                Lead.organization_id == row.organization_id,
                Lead.archived_at.is_(None),
            )
        )
        if lead is None:
            raise AppError(404, "lead_not_found", "Lead not found")
        origin = lead.origin
        payload["new_status"] = lead.status.value
    if body.opportunity_id:
        opportunity = db.scalar(
            select(Opportunity).where(
                Opportunity.id == body.opportunity_id,
                Opportunity.organization_id == row.organization_id,
                Opportunity.archived_at.is_(None),
            )
        )
        if opportunity is None:
            raise AppError(404, "opportunity_not_found", "Opportunity not found")
        payload.update(opportunity_id=str(opportunity.id), new_stage=opportunity.stage)
    enforce_limit(db, row.organization_id, "active_workflows")
    run = WorkflowRun(
        organization_id=row.organization_id,
        kind=WorkflowKind.follow_up,
        status=WorkflowStatus.pending,
        idempotency_key=key,
        lead_id=body.lead_id,
        payload=payload,
        origin=origin,
    )
    db.add(run)
    db.flush()
    record_event(
        db,
        row.organization_id,
        "workflow_manual_run",
        {"run_id": str(run.id), "workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
    db.commit()
    return _run_out(run)


@router.post("/{workflow_id}/runs/{run_id}/retry")
def retry_run(
    workflow_id: uuid.UUID, run_id: uuid.UUID, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = _get_definition(workflow_id, admin, db, lock=True)
    run = db.scalar(_run_query(row).where(WorkflowRun.id == run_id).with_for_update())
    if run is None:
        raise AppError(404, "workflow_run_not_found", "Workflow run not found")
    steps = run.payload.get("steps") or []
    local_failure = any(isinstance(step, dict) and step.get("status") == "failed" for step in steps)
    if run.status != WorkflowStatus.failed or not local_failure:
        raise AppError(
            409,
            "workflow_retry_unavailable",
            "This run cannot be repeated safely. Start a new test instead.",
        )
    payload = dict(run.payload)
    payload.pop("steps", None)
    payload.pop("outcome", None)
    payload.pop("approval_id", None)
    run.payload = payload
    run.status = WorkflowStatus.pending
    run.last_error = None
    db.commit()
    return _run_out(run)


class ReviewBody(BaseModel):
    decision: Literal["approve", "reject"]


@router.post("/{workflow_id}/runs/{run_id}/review")
def review_run(
    workflow_id: uuid.UUID, run_id: uuid.UUID, body: ReviewBody, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = _get_definition(workflow_id, admin, db, lock=True)
    run = db.scalar(_run_query(row).where(WorkflowRun.id == run_id).with_for_update())
    if run is None:
        raise AppError(404, "workflow_run_not_found", "Workflow run not found")
    if run.status != WorkflowStatus.accepted or run.payload.get("outcome") != "awaiting_approval":
        raise AppError(
            409, "workflow_review_unavailable", "This workflow run is no longer awaiting approval"
        )
    if body.decision == "approve" and row.archived_at is not None:
        raise AppError(409, "workflow_archived", "Archived workflow runs can only be rejected")
    payload = {
        **run.payload,
        "review": {"decision": body.decision, "decided_at": datetime.now(UTC).isoformat()},
    }
    payload.pop("outcome", None)
    if body.decision == "reject":
        payload["outcome"] = "rejected"
    run.payload = payload
    run.status = WorkflowStatus.pending if body.decision == "approve" else WorkflowStatus.completed
    record_event(
        db,
        row.organization_id,
        f"workflow_run_{body.decision}",
        {"run_id": str(run.id), "workflow_id": str(row.id)},
        actor_id=admin.user.id,
    )
    db.commit()
    return _run_out(run)
