import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_password
from app.domains.crm.models import Company
from app.domains.identity.models import Organization, User
from app.scripts.bootstrap import (
    BootstrapRefused,
    BootstrapRequest,
    create_first_administrator,
    main,
    status_line,
)

REQUEST = {
    "organization_name": "Harbor Staging",
    "organization_slug": "harbor",
    "email": "admin@harbor.example",
    "full_name": "Ada Admin",
    "password": "staging-bootstrap-pass",
}


def test_bootstrap_creates_one_admin_and_no_demo_records(db: Session) -> None:
    organization, user = create_first_administrator(db, BootstrapRequest.model_validate(REQUEST))

    assert organization.slug == "harbor"
    assert user.email == "admin@harbor.example"
    assert verify_password(REQUEST["password"], user.password_hash)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Organization)) == 1
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    assert "users=1 organizations=1 administrators=1 companies=0" in status_line(db)


def test_bootstrap_refuses_to_overwrite_an_administrator(db: Session) -> None:
    create_first_administrator(db, BootstrapRequest.model_validate(REQUEST))
    replacement = dict(REQUEST)
    replacement["password"] = "another-staging-secret"
    replacement["full_name"] = "Replacement Admin"
    with pytest.raises(BootstrapRefused, match="administrator_exists"):
        create_first_administrator(db, BootstrapRequest.model_validate(replacement))

    stored = db.scalar(select(User).where(User.email == "admin@harbor.example"))
    assert stored is not None
    assert stored.full_name == "Ada Admin"
    assert verify_password(REQUEST["password"], stored.password_hash)
    assert not verify_password(replacement["password"], stored.password_hash)
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_bootstrap_allows_production(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    production = get_settings().model_copy(
        update={"environment": "production", "public_demo": False}
    )
    monkeypatch.setattr("app.scripts.bootstrap.get_settings", lambda: production)
    create_first_administrator(db, BootstrapRequest.model_validate(REQUEST))
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_bootstrap_refuses_a_public_demo(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    demo = get_settings().model_copy(update={"public_demo": True})
    monkeypatch.setattr("app.scripts.bootstrap.get_settings", lambda: demo)
    with pytest.raises(BootstrapRefused, match="public_demo"):
        create_first_administrator(db, BootstrapRequest.model_validate(REQUEST))
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_bootstrap_command_hides_the_password(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    del db
    code = main(stdin_text=json.dumps(REQUEST), env={})
    captured = capsys.readouterr()
    assert code == 0
    assert "bootstrap_ok" in captured.out
    assert REQUEST["password"] not in captured.out
    assert REQUEST["password"] not in captured.err

    again = dict(REQUEST)
    again["password"] = "replacement-staging-secret"
    refused = main(stdin_text=json.dumps(again), env={})
    refused_out = capsys.readouterr().out
    assert refused == 2
    assert "bootstrap_refused reason=administrator_exists" in refused_out
    assert again["password"] not in refused_out


def test_bootstrap_rejects_a_placeholder_password(capsys: pytest.CaptureFixture[str]) -> None:
    payload = dict(REQUEST)
    payload["password"] = "change-me-change-me"
    code = main(stdin_text=json.dumps(payload), env={})
    captured = capsys.readouterr().out
    assert code == 2
    assert "bootstrap_refused reason=weak_password" in captured
    assert payload["password"] not in captured
