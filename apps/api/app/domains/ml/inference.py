"""Score one CRM lead. The result is stored and does not change the lead."""

import threading
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.crm.models import Company, Contact, Lead
from app.domains.ml.models import LeadPrediction, ModelVersion
from app.domains.ml.training import load_pipeline, publish_model

logger = structlog.get_logger(__name__)
_TRAINING = threading.Lock()


def start_training() -> str:
    if not _TRAINING.acquire(blocking=False):
        return "running"

    def _train() -> None:
        try:
            with SessionLocal() as db:
                publish_model(db)
        except Exception:
            logger.error("lead_training_failed")
        finally:
            _TRAINING.release()

    threading.Thread(target=_train, name="atlas-lead-training", daemon=True).start()
    return "started"


def latest_model(db: Session) -> ModelVersion | None:
    return db.scalar(select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(1))


def score_lead(db: Session, organization_id: uuid.UUID, lead: Lead) -> LeadPrediction:
    version = latest_model(db)
    if version is None:
        raise AppError(503, "model_unavailable", "No trained lead model is available")
    try:
        bundle = load_pipeline(version)
        pipeline = bundle["pipeline"]
        calibrator = bundle.get("calibrator")
        explainer = bundle.get("explainer")
    except (OSError, FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise AppError(
            503, "model_unavailable", "The trained lead model could not be loaded"
        ) from exc
    features = _features(db, organization_id, lead)
    try:
        probability = _positive_probability(calibrator or pipeline, features)
        label = "likely" if pipeline.predict([features])[0] == 1 else "unlikely"
        contributions = _contributions(explainer, features)
    except (IndexError, ValueError, AttributeError) as exc:
        raise AppError(503, "model_failed", "The lead model could not score this lead") from exc
    prediction = LeadPrediction(
        organization_id=organization_id,
        lead_id=lead.id,
        model_version_id=version.id,
        label=label,
        probability=probability,
        confidence=probability,
        contributions=contributions,
        synthetic=True,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


def latest_prediction(
    db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> LeadPrediction | None:
    return db.scalar(
        select(LeadPrediction)
        .where(
            LeadPrediction.organization_id == organization_id,
            LeadPrediction.lead_id == lead_id,
        )
        .order_by(LeadPrediction.created_at.desc())
        .limit(1)
    )


def _features(db: Session, organization_id: uuid.UUID, lead: Lead) -> list[object]:
    has_email = 0
    if lead.contact_id is not None:
        contact = db.get(Contact, lead.contact_id)
        if contact is not None and contact.organization_id == organization_id and contact.email:
            has_email = 1
    industry = "unknown"
    has_company = 0
    if lead.company_id is not None:
        company = db.get(Company, lead.company_id)
        if company is not None and company.organization_id == organization_id:
            has_company = 1
            if company.industry:
                industry = company.industry
    source = (lead.source or "unknown").strip() or "unknown"
    return [source, has_email, has_company, len(lead.title), len(lead.notes or ""), industry]


def _contributions(pipeline: Any, features: list[object]) -> list[dict[str, Any]]:
    model = pipeline.named_steps.get("model")
    prepare = pipeline.named_steps.get("prepare")
    if model is None or prepare is None or not hasattr(model, "coef_"):
        return []
    transformed = prepare.transform([features])
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    names = [str(name) for name in prepare.get_feature_names_out()]
    weights = [float(value) for value in model.coef_[0]]
    ranked = [
        {"feature": name, "contribution": round(float(row) * weight, 6)}
        for name, row, weight in zip(names, transformed[0], weights, strict=True)
    ]
    ranked.sort(key=_magnitude, reverse=True)
    return ranked[:5]


def _positive_probability(model: Any, features: list[object]) -> float:
    return float(model.predict_proba([features])[0][1])


def _magnitude(item: dict[str, Any]) -> float:
    value = item["contribution"]
    if isinstance(value, int | float):
        return abs(value)
    return 0.0
