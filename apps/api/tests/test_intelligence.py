import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.analytics.service import snapshot
from app.domains.crm.models import Lead, LeadStatus
from app.domains.evaluation.service import run_evaluation
from app.domains.identity.models import MembershipRole
from app.domains.ml.dataset import FEATURES, generate_leads, matrix
from app.domains.ml.training import publish_model, train_lead_model
from app.domains.observability.models import OperationTrace
from app.domains.observability.tracing import estimate_cost, record_operation, redact
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _org(payload: dict[str, object]) -> str:
    memberships = payload["memberships"]
    assert isinstance(memberships, list)
    first = memberships[0]
    assert isinstance(first, dict)
    return str(first["organization_id"])


def _csrf(payload: dict[str, object]) -> dict[str, str]:
    return {"X-CSRF-Token": str(payload["csrf_token"])}


def test_training_is_reproducible_and_excludes_the_label() -> None:
    first = train_lead_model()
    second = train_lead_model()
    assert first["metrics"] == second["metrics"]
    assert first["comparison"] == second["comparison"]
    assert first["synthetic"] is True
    assert first["calibrated"] is True
    forbidden = {"budget_band", "converted", "status", "revenue"}
    assert forbidden.isdisjoint(FEATURES)
    features, _labels = matrix(generate_leads())
    assert len(features[0]) == len(FEATURES)
    assert "precision" in first["metrics"]
    assert "recall" in first["metrics"]
    assert "f1" in first["metrics"]


def test_prediction_is_advisory_and_isolated(client: TestClient, db: Session) -> None:
    admin = make_user(db, "score-admin@example.com")
    outsider = make_user(db, "score-out@example.org")
    atlas = make_organization(db, "Score Atlas", "score-atlas")
    other = make_organization(db, "Score Other", "score-other")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(client, "score-admin@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Harbor expansion", "source": "referral", "status": "new"},
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    missing = client.post(
        f"/api/v1/organizations/{org}/leads/{lead_id}/predictions",
        headers=headers,
    )
    assert missing.status_code == 503
    assert missing.json()["error"]["code"] == "model_unavailable"
    publish_model(db)
    scored = client.post(
        f"/api/v1/organizations/{org}/leads/{lead_id}/predictions",
        headers=headers,
    )
    assert scored.status_code == 201, scored.text
    body = scored.json()
    assert body["synthetic"] is True
    assert body["label"] in {"likely", "unlikely"}
    assert "artifact" not in body
    assert "Synthetic-data demonstration" in body["notice"]
    stored = db.get(Lead, uuid.UUID(lead_id))
    assert stored is not None
    assert stored.status == LeadStatus.new
    listed = client.get(f"/api/v1/organizations/{org}/leads/{lead_id}/predictions")
    assert listed.status_code == 200
    assert listed.json()["id"] == body["id"]
    model = client.get(f"/api/v1/organizations/{org}/ml/model")
    assert model.status_code == 200
    assert "artifact_path" not in model.json()
    outsider_session = login(client, "score-out@example.org", PASSWORD)
    hidden = client.get(
        f"/api/v1/organizations/{_org(outsider_session)}/leads/{lead_id}/predictions"
    )
    assert hidden.status_code == 404


def test_analytics_defines_empty_and_conversion(client: TestClient, db: Session) -> None:
    admin = make_user(db, "metrics@example.com")
    outsider = make_user(db, "metrics-out@example.org")
    atlas = make_organization(db, "Metrics Atlas", "metrics-atlas")
    other = make_organization(db, "Metrics Other", "metrics-other")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(client, "metrics@example.com", PASSWORD)
    org = _org(ada)
    empty = client.get(f"/api/v1/organizations/{org}/analytics")
    assert empty.status_code == 200
    payload = empty.json()
    assert payload["leads_total"] == 0
    assert payload["conversion"]["rate"] is None
    assert payload["conversion"]["denominator"] == 0
    assert payload["automation"]["success_rate"] is None
    assert len(payload["lead_trend"]) == payload["window_days"]
    headers = _csrf(ada)
    for status in ("won", "lost"):
        created = client.post(
            f"/api/v1/organizations/{org}/leads",
            json={"title": f"Lead {status}", "status": status},
            headers=headers,
        )
        assert created.status_code == 201, created.text
    filled = snapshot(db, uuid.UUID(org))
    assert filled["leads_total"] == 2
    assert filled["conversion"]["rate"] == 0.5
    outsider_session = login(client, "metrics-out@example.org", PASSWORD)
    foreign = client.get(f"/api/v1/organizations/{_org(outsider_session)}/analytics")
    assert foreign.json()["leads_total"] == 0


def test_evaluation_records_deterministic_results(db: Session) -> None:
    admin = make_user(db, "eval@example.com")
    atlas = make_organization(db, "Eval Atlas", "eval-atlas")
    make_membership(db, admin, atlas, MembershipRole.admin)
    row = run_evaluation(db, atlas.id)
    assert row.method == "deterministic_double"
    assert row.executed_count == row.passed_count
    assert row.executed_count >= 8
    assert row.results["live_model"] is False
    assert row.results["failure_cases"] == []


def test_traces_redact_secrets_and_skip_unknown_cost(db: Session, monkeypatch) -> None:
    admin = make_user(db, "trace@example.com")
    atlas = make_organization(db, "Trace Atlas", "trace-atlas")
    make_membership(db, admin, atlas, MembershipRole.admin)
    cleaned = redact({"X-ATLAS-Signature": "secret-value", "lead_id": "visible"})
    assert cleaned["X-ATLAS-Signature"] == "[redacted]"
    assert cleaned["lead_id"] == "visible"
    unpriced = get_settings().model_copy(
        update={"llm_input_usd_per_million": None, "llm_output_usd_per_million": None}
    )
    monkeypatch.setattr("app.domains.observability.tracing.get_settings", lambda: unpriced)
    assert estimate_cost(1000, 500) is None
    record_operation(
        operation="chat_usage",
        status="succeeded",
        organization_id=atlas.id,
        tokens_in=1000,
        tokens_out=500,
        detail={"authorization": "Bearer hidden"},
    )
    row = db.scalar(select(OperationTrace).where(OperationTrace.organization_id == atlas.id))
    assert row is not None
    assert row.cost_usd is None
    assert row.langfuse_status == "unconfigured"
    assert row.detail["authorization"] == "[redacted]"
    priced = unpriced.model_copy(
        update={"llm_input_usd_per_million": 1.0, "llm_output_usd_per_million": 2.0}
    )
    monkeypatch.setattr("app.domains.observability.tracing.get_settings", lambda: priced)
    assert estimate_cost(1_000_000, 1_000_000) == 3.0


def test_langfuse_failure_keeps_the_local_trace(db: Session, monkeypatch) -> None:
    admin = make_user(db, "langfuse@example.com")
    atlas = make_organization(db, "Langfuse Atlas", "langfuse-atlas")
    make_membership(db, admin, atlas, MembershipRole.admin)
    configured = get_settings().model_copy(
        update={"langfuse_public_key": "pk-test", "langfuse_secret_key": "sk-test"}
    )
    monkeypatch.setattr("app.domains.observability.tracing.get_settings", lambda: configured)

    def explode(_payload: dict[str, object]) -> str:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr("app.domains.observability.tracing.export_langfuse", explode)
    record_operation(operation="retrieval", status="succeeded", organization_id=atlas.id, detail={})
    row = db.scalar(select(OperationTrace).where(OperationTrace.organization_id == atlas.id))
    assert row is not None
    assert row.langfuse_status == "unavailable"
