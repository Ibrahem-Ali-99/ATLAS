"""Small timings against the test database and deterministic providers.

This is not live model latency. The API runs inside this process.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _working_set_bytes() -> int | None:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Process -Id {os.getpid()}).WorkingSet64",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    text = completed.stdout.strip()
    if completed.returncode != 0 or not text.isdigit():
        return None
    return int(text)


def _container_stats() -> list[dict[str, str]]:
    completed = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    rows: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        name, _, rest = line.partition("\t")
        if not name.startswith("atlas-"):
            continue
        cpu, _, memory = rest.partition("\t")
        rows.append({"name": name, "cpu": cpu, "memory": memory})
    return rows


def main() -> None:
    os.environ["ATLAS_LLM_PROVIDER"] = "double"
    os.environ["ATLAS_EMBEDDING_PROVIDER"] = "double"
    from sqlalchemy import text

    from tests.bootstrap import ensure_database

    ensure_database("atlas_test")
    from fastapi.testclient import TestClient

    from app.core.database import SessionLocal, engine
    from app.domains.identity.models import MembershipRole
    from app.main import create_app
    from tests.factories import PASSWORD, make_membership, make_organization, make_user

    db = SessionLocal()
    try:
        user = make_user(db, "bench@example.com")
        organization = make_organization(db, "Bench", "bench-latency")
        make_membership(db, user, organization, MembershipRole.admin)
    finally:
        db.close()
    timings: dict[str, Any] = {
        "environment": "Windows host process, atlas_test, deterministic providers",
        "live_model": False,
    }
    with engine.connect() as connection:
        started = time.perf_counter()
        connection.execute(text("SELECT count(*) FROM leads"))
        timings["lead_count_query_ms"] = _elapsed(started)
        plan = connection.execute(text("EXPLAIN SELECT count(*) FROM leads")).scalars().all()
        timings["lead_count_plan"] = str(plan[0]) if plan else ""
    with TestClient(create_app()) as client:
        started = time.perf_counter()
        health = client.get("/api/v1/health")
        timings["health_ms"] = _elapsed(started)
        assert health.status_code == 200
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "bench@example.com", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        org = login.json()["memberships"][0]["organization_id"]
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        started = time.perf_counter()
        leads = client.get(f"/api/v1/organizations/{org}/leads")
        timings["crm_list_ms"] = _elapsed(started)
        assert leads.status_code == 200
        uploaded = client.post(
            f"/api/v1/organizations/{org}/documents",
            headers=headers,
            files={
                "file": (
                    "bench-harbor.txt",
                    b"Harbor warehousing includes bonded yards.",
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        started = time.perf_counter()
        found = client.get(
            f"/api/v1/organizations/{org}/documents/search",
            params={"q": "bonded yards"},
        )
        timings["retrieval_ms"] = _elapsed(started)
        assert found.status_code == 200, found.text
        assert found.json()["items"], found.text
        inquiry = client.post(
            f"/api/v1/organizations/{org}/inquiries",
            headers=headers,
            json={"subject": "Bench", "body": "Mina Patel asked about bonded storage."},
        )
        assert inquiry.status_code == 201, inquiry.text
        started = time.perf_counter()
        run = client.post(
            f"/api/v1/organizations/{org}/agent-runs",
            headers=headers,
            json={"inquiry_id": inquiry.json()["id"]},
        )
        timings["agent_to_approval_ms"] = _elapsed(started)
        assert run.status_code == 201, run.text
        assert run.json()["run"]["status"] == "awaiting_approval"
    timings["process_working_set_bytes"] = _working_set_bytes()
    timings["containers"] = _container_stats()
    print(json.dumps(timings, indent=2))


if __name__ == "__main__":
    main()
