import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.crm.models import Inquiry
from app.scripts.reset_demo import assert_reset_allowed, database_name, reset_demo_activity
from tests.factories import make_organization, make_user


def test_reset_refuses_without_the_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={"environment": "development", "public_demo": False}
    )
    monkeypatch.setattr("app.scripts.reset_demo.get_settings", lambda: settings)
    monkeypatch.delenv("ATLAS_DEMO_RESET", raising=False)
    with pytest.raises(RuntimeError, match="ATLAS_DEMO_RESET"):
        assert_reset_allowed(settings.database_url)


def test_reset_refuses_a_public_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"environment": "development", "public_demo": True})
    monkeypatch.setattr("app.scripts.reset_demo.get_settings", lambda: settings)
    monkeypatch.setenv("ATLAS_DEMO_RESET", "yes")
    with pytest.raises(RuntimeError, match="public demo"):
        assert_reset_allowed(settings.database_url)


def test_reset_removes_failed_activity_and_keeps_the_password(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(
        update={"environment": "development", "public_demo": False}
    )
    monkeypatch.setattr("app.scripts.reset_demo.get_settings", lambda: settings)
    monkeypatch.setenv("ATLAS_DEMO_RESET", "yes")
    assert database_name(settings.database_url) == "atlas_test"
    assert_reset_allowed(settings.database_url)
    user = make_user(db, "reset-demo@example.com")
    password_hash = user.password_hash
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    inquiry = Inquiry(
        organization_id=organization.id,
        subject="Day 5 unconfigured run",
        body="Synthetic failure kept for diagnostics.",
    )
    db.add(inquiry)
    db.flush()
    run = AgentRun(
        organization_id=organization.id,
        inquiry_id=inquiry.id,
        started_by=user.id,
        status=RunStatus.failed,
        error_code="llm_unconfigured",
        error_message="The language model is not configured.",
    )
    db.add(run)
    db.commit()
    reset_demo_activity(db, organization.id)
    assert db.get(AgentRun, run.id) is None
    assert db.get(type(user), user.id).password_hash == password_hash
    assert db.get(Inquiry, inquiry.id) is not None
