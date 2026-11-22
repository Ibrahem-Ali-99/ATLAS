import json
import threading
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.assistant.service import NO_RECORDS
from app.domains.automation.signatures import signatures_match
from app.domains.ml.dataset import FEATURES, baseline_predict, generate_leads
from app.domains.observability.models import EvaluationRun
from app.domains.observability.tracing import redact
from app.integrations.language import OpenAICompatibleChatClient
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

logger = structlog.get_logger(__name__)
DATASET_PATH = Path(__file__).with_name("benchmark_v1.json")
_EVALUATION = threading.Lock()


def load_benchmark() -> dict[str, Any]:
    loaded = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AppError(500, "benchmark_invalid", "The evaluation dataset could not be read")
    return loaded


def run_evaluation(db: Session, organization_id: uuid.UUID) -> EvaluationRun:
    benchmark = load_benchmark()
    scenarios = benchmark["scenarios"]
    results = [_run_check(item) for item in scenarios]
    passed = sum(1 for item in results if item["passed"])
    failures = [item for item in results if not item["passed"]]
    row = EvaluationRun(
        organization_id=organization_id,
        dataset_version=str(benchmark["version"]),
        method=str(benchmark["method"]),
        model_configuration="deterministic_double; no live provider",
        status="completed",
        executed_count=len(results),
        passed_count=passed,
        results={
            "notice": benchmark["notice"],
            "scenarios": results,
            "failure_cases": failures,
            "live_model": False,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def start_evaluation(organization_id: uuid.UUID) -> str:
    if not _EVALUATION.acquire(blocking=False):
        return "running"

    def _run() -> None:
        try:
            with SessionLocal() as db:
                run_evaluation(db, organization_id)
        except Exception:
            logger.error("evaluation_failed", organization_id=str(organization_id))
        finally:
            _EVALUATION.release()

    threading.Thread(target=_run, name="atlas-evaluation", daemon=True).start()
    return "started"


def list_evaluations(db: Session, organization_id: uuid.UUID) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.organization_id == organization_id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(10)
        )
    )


def _run_check(scenario: dict[str, Any]) -> dict[str, Any]:
    check = str(scenario["check"])
    try:
        evidence = _CHECKS[check]()
        passed = True
        error = None
    except Exception as exc:
        evidence = ""
        passed = False
        error = type(exc).__name__
    return {
        "id": scenario["id"],
        "group": scenario["group"],
        "method": "deterministic_double",
        "passed": passed,
        "evidence": evidence,
        "error": error,
    }


def _empty_refusal() -> str:
    if not NO_RECORDS or "model" in NO_RECORDS.lower():
        raise AssertionError("empty retrieval must refuse without inventing a model answer")
    return "empty retrieval uses the stored refusal and does not call a model"


def _feature_isolation() -> str:
    forbidden = {"budget_band", "converted", "status", "revenue"}
    if forbidden & set(FEATURES):
        raise AssertionError("a scoring feature leaks the label or a hidden field")
    return "lead features exclude the synthetic label, budget band, status, and revenue"


def _baseline_stable() -> str:
    row = [["referral", 1, 1, 20, 0, "logistics"]]
    other = [["website", 1, 1, 20, 0, "logistics"]]
    if baseline_predict(row) != [1] or baseline_predict(other) != [0]:
        raise AssertionError("the referral rule changed")
    return "the baseline predicts likely only when the source is referral"


def _signature_mismatch() -> str:
    if signatures_match("abc", "abd") or not signatures_match("abc", "abc"):
        raise AssertionError("signature comparison is not exact")
    return "a changed webhook signature does not match"


def _missing_llm() -> str:
    settings = Settings(
        _env_file=None,
        environment="test",
        secret_key="test-secret-key-must-be-32-chars-min",
        database_url="postgresql+psycopg://atlas:atlas@localhost:5432/atlas",
        llm_api_key="",
    )
    try:
        OpenAICompatibleChatClient(settings).ensure_configured()
    except AppError as exc:
        if exc.code != "llm_unconfigured":
            raise
        return "an empty chat key fails before a provider request"
    raise AssertionError("an empty chat key was accepted")


def _uncertain_not_retried() -> str:
    uncertain = OutcomeUncertain("smtp_timeout")
    failed = DeliveryFailed("smtp_failed")
    if str(uncertain) == str(failed):
        raise AssertionError("uncertain and refused delivery were collapsed")
    if str(uncertain) != "smtp_timeout":
        raise AssertionError("the uncertain code changed")
    return "smtp_timeout stays an uncertain outcome and is distinct from smtp_failed"


def _redact_secrets() -> str:
    cleaned = redact(
        {
            "X-ATLAS-Signature": "abc",
            "authorization": "Bearer secret",
            "lead_id": "ok",
        }
    )
    if cleaned["X-ATLAS-Signature"] != "[redacted]" or cleaned["authorization"] != "[redacted]":
        raise AssertionError("a credential survived redaction")
    if cleaned["lead_id"] != "ok":
        raise AssertionError("a non-secret field was removed")
    return "signature and authorization values are redacted"


def _dataset_repeat() -> str:
    if generate_leads() != generate_leads():
        raise AssertionError("the synthetic lead dataset changed between identical seeds")
    return "the synthetic dataset repeats for the documented seed"


_CHECKS = {
    "empty_refusal": _empty_refusal,
    "feature_isolation": _feature_isolation,
    "baseline_stable": _baseline_stable,
    "signature_mismatch": _signature_mismatch,
    "missing_llm": _missing_llm,
    "uncertain_not_retried": _uncertain_not_retried,
    "redact_secrets": _redact_secrets,
    "dataset_repeat": _dataset_repeat,
}
