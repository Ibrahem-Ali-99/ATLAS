import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.identity.models import Membership, Organization, User
from app.scripts.seed import SeedSettings, seed_identity

SEED = dict(
    seed_admin_email="admin@example.com",
    seed_admin_password="change-me-admin",
    seed_admin_name="Avery Admin",
    seed_staff_email="staff@example.com",
    seed_staff_password="change-me-staff",
    seed_staff_name="Sam Staff",
    seed_outsider_email="outsider@example.org",
    seed_outsider_password="change-me-outsider",
    seed_outsider_name="Olivia Outsider",
)


def test_seed_is_idempotent_and_isolates_tenants(client: TestClient, db: Session) -> None:
    settings = SeedSettings(_env_file=None, **SEED)
    seed_identity(db, settings)
    seed_identity(db, settings)

    assert db.scalar(select(func.count()).select_from(User)) == 3
    assert db.scalar(select(func.count()).select_from(Organization)) == 2
    assert db.scalar(select(func.count()).select_from(Membership)) == 3

    admin = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "change-me-admin"},
    )
    assert admin.status_code == 200
    slugs = {item["organization_slug"] for item in admin.json()["memberships"]}
    assert slugs == {"atlas-demo"}

    client.cookies.clear()
    staff = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@example.com", "password": "change-me-staff"},
    )
    assert staff.status_code == 200
    assert staff.json()["memberships"][0]["role"] == "staff"
    assert staff.json()["memberships"][0]["organization_slug"] == "atlas-demo"


def test_seed_refuses_production_and_public_demo(db: Session, monkeypatch) -> None:
    blocked = get_settings().model_copy(update={"public_demo": True})
    monkeypatch.setattr("app.scripts.seed.get_settings", lambda: blocked)
    with pytest.raises(RuntimeError, match="public demo"):
        seed_identity(db, SeedSettings(_env_file=None, **SEED))
