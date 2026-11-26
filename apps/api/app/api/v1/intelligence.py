import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.analytics.service import snapshot
from app.domains.crm import service as crm
from app.domains.evaluation.service import list_evaluations, start_evaluation
from app.domains.identity.dependencies import CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.identity.models import Membership
from app.domains.ml.inference import latest_model, latest_prediction, score_lead, start_training
from app.domains.ml.models import LeadPrediction, ModelVersion
from app.domains.monitoring.service import diagnostics, trace_run
from app.domains.provenance.origin import DataScope

router = APIRouter(prefix="/organizations/{organization_id}", tags=["intelligence"])
SYNTHETIC_NOTICE = (
    "Synthetic-data demonstration. This score does not measure real conversion "
    "and does not authorize a CRM change or an external action."
)


class PredictionOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    label: str
    probability: float
    confidence: float | None
    contributions: list[dict[str, Any]]
    synthetic: bool
    model_version: str
    notice: str
    explanation: str


@router.get("/analytics")
def get_analytics(
    member: Member,
    db: DbSession,
    scope: DataScope = DataScope.operational,
    period: str = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    owner_user_id: uuid.UUID | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    if period not in {"7d", "30d", "90d", "custom"}:
        raise AppError(422, "invalid_analytics_period", "Unsupported analytics period")
    if period == "custom":
        if start_date is None or end_date is None or not 0 <= (end_date - start_date).days <= 365:
            raise AppError(
                422, "invalid_analytics_dates", "Choose an ordered date range of up to 366 days"
            )
        days = (end_date - start_date).days + 1
    else:
        days = int(period[:-1])
        start_date = end_date = None
    if channel is not None and channel not in {"email", "whatsapp", "webchat", "website", "sms"}:
        raise AppError(422, "invalid_analytics_channel", "Unsupported conversation channel")
    if (
        owner_user_id is not None
        and db.scalar(
            select(Membership.id).where(
                Membership.organization_id == member.organization.id,
                Membership.user_id == owner_user_id,
            )
        )
        is None
    ):
        raise AppError(404, "owner_not_found", "Opportunity owner is not in this organization")
    return snapshot(
        db,
        member.organization.id,
        scope,
        days=days,
        start_date=start_date,
        end_date=end_date,
        owner_user_id=owner_user_id,
        channel=channel,
    )


@router.get("/ml/model")
def get_model(member: Member, db: DbSession) -> dict[str, Any]:
    version = latest_model(db)
    if version is None:
        raise AppError(404, "model_unavailable", "No trained lead model is available")
    return {
        "version": version.version,
        "algorithm": version.algorithm,
        "dataset_version": version.dataset_version,
        "synthetic": version.synthetic,
        "metrics": version.metrics,
        "notice": SYNTHETIC_NOTICE,
    }


@router.post("/ml/train", status_code=202)
def train_model(member: CsrfAdmin) -> JSONResponse:
    return JSONResponse(status_code=202, content={"status": start_training()})


@router.post("/leads/{lead_id}/predictions", response_model=PredictionOut, status_code=201)
def create_prediction(lead_id: uuid.UUID, member: CsrfMember, db: DbSession) -> PredictionOut:
    lead = crm.get_lead(db, member.organization.id, lead_id)
    prediction = score_lead(db, member.organization.id, lead)
    version = latest_model(db)
    return _prediction_out(prediction, version)


@router.get("/leads/{lead_id}/predictions", response_model=PredictionOut)
def get_prediction(lead_id: uuid.UUID, member: Member, db: DbSession) -> PredictionOut:
    crm.get_lead(db, member.organization.id, lead_id)
    prediction = latest_prediction(db, member.organization.id, lead_id)
    if prediction is None:
        raise AppError(404, "not_found", "Resource not found")
    version = latest_model(db)
    return _prediction_out(prediction, version)


@router.post("/evaluations", status_code=202)
def create_evaluation(member: CsrfAdmin) -> JSONResponse:
    return JSONResponse(
        status_code=202, content={"status": start_evaluation(member.organization.id)}
    )


@router.get("/evaluations")
def get_evaluations(member: Member, db: DbSession) -> dict[str, Any]:
    rows = list_evaluations(db, member.organization.id)
    return {
        "notice": "Results are deterministic checks. They are not live-model accuracy.",
        "items": [
            {
                "id": row.id,
                "dataset_version": row.dataset_version,
                "method": row.method,
                "model_configuration": row.model_configuration,
                "status": row.status,
                "executed_count": row.executed_count,
                "passed_count": row.passed_count,
                "results": row.results,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.get("/diagnostics")
def get_diagnostics(
    member: Member, db: DbSession, scope: DataScope = DataScope.operational
) -> dict[str, Any]:
    return diagnostics(db, member.organization.id, scope)


@router.get("/diagnostics/runs/{run_id}")
def get_diagnostic_run(run_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, Any]:
    return trace_run(db, member.organization.id, run_id)


def _prediction_out(prediction: LeadPrediction, version: ModelVersion | None) -> PredictionOut:
    algorithm = "" if version is None else version.algorithm
    if algorithm == "decision_tree":
        explanation = "Each step is a split on the served decision tree."
    elif algorithm == "logistic_regression":
        explanation = "Each step is a coefficient from the served logistic model."
    else:
        explanation = "Feature influence is unavailable for this model."
    return PredictionOut(
        id=prediction.id,
        lead_id=prediction.lead_id,
        label=prediction.label,
        probability=prediction.probability,
        confidence=prediction.confidence,
        contributions=list(prediction.contributions),
        synthetic=True,
        model_version="" if version is None else version.version,
        notice=SYNTHETIC_NOTICE,
        explanation=explanation,
    )
