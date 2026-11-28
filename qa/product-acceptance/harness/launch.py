"""Start an isolated acceptance stack and write the defect register.

Does not restart the shared API or web app, does not print secrets, and does not
open checkout, send mail, or dispatch n8n.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote_plus

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"
WEB = REPO / "apps" / "web-rebuild"
QA = REPO / "qa" / "product-acceptance"
sys.path.insert(0, str(API))
sys.path.insert(0, str(QA))

from harness.blackbox import run as run_blackbox  # noqa: E402
from harness.client import ApiSession  # noqa: E402
from harness.register import write_register  # noqa: E402
from harness.walk import finish_agent, run as run_walk  # noqa: E402


def main() -> int:
    evidence = REPO / "var" / "product-acceptance" / time.strftime("%Y%m%d-%H%M%S")
    evidence.mkdir(parents=True)
    shared_before = _shared_health()
    api_port = _free_port(8097)
    web_port = _free_port(3097)
    database = "atlas_e2e_" + uuid.uuid4().hex
    api_log = open(evidence / "api.log", "w", encoding="utf-8")
    web_log = open(evidence / "web.log", "w", encoding="utf-8")
    api_proc = None
    web_proc = None
    session_file = evidence / "browser-session.json"
    summary: dict[str, object] = {
        "evidence": str(evidence),
        "api_port": api_port,
        "web_port": web_port,
        "database": database,
        "shared_before": shared_before,
    }
    try:
        _prepare_database(database, evidence)
        api_proc = _start_api(api_port, web_port, database, api_log)
        _wait_http(f"http://127.0.0.1:{api_port}/api/v1/ready", api_proc, evidence / "api.log", 90)
        web_proc = _start_web(web_port, api_port, web_log)
        _wait_http(f"http://127.0.0.1:{web_port}/login", web_proc, evidence / "web.log", 180)
        from app.scripts.seed import SeedSettings

        seed = SeedSettings()
        admin = ApiSession(f"http://127.0.0.1:{api_port}", str(seed.seed_admin_email), seed.seed_admin_password)
        staff = ApiSession(f"http://127.0.0.1:{api_port}", str(seed.seed_staff_email), seed.seed_staff_password)
        outsider = ApiSession(
            f"http://127.0.0.1:{api_port}", str(seed.seed_outsider_email), seed.seed_outsider_password
        )
        try:
            walked = run_walk(admin, outsider, evidence)
            assistant = run_blackbox(admin, staff, evidence, walked["context"])
            walked["findings"].extend(finish_agent(admin, staff, walked["context"]))
            walked["findings"].extend(assistant["findings"])
            _write_browser_session(session_file, web_port, evidence, seed)
            ui = _run_browser(session_file, evidence)
            walked["findings"].extend(ui.get("findings") or [])
            walked["passed"].extend(ui.get("passed") or [])
            _integration_findings(walked, evidence)
            summary["passed"] = walked["passed"]
            summary["context"] = walked["context"]
            summary["assistant"] = {
                "failed": assistant["failed"],
                "total": assistant["total"],
            }
            summary["findings"] = [item["id"] for item in walked["findings"]]
        finally:
            admin.close()
            staff.close()
            outsider.close()
        summary["shared_after"] = _shared_health()
        (evidence / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        register = write_register(evidence / "DEFECTS.md", summary, walked["findings"])
        print(f"acceptance_evidence={evidence}")
        print(f"defect_register={register}")
        print(f"findings={len(walked['findings'])} passed_checks={len(walked['passed'])}")
        print(f"shared_api={summary['shared_after'].get('api')} shared_web={summary['shared_after'].get('web')}")
        return 0
    except Exception as exc:
        summary["error"] = str(exc)[:500]
        summary["shared_after"] = _shared_health()
        (evidence / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"acceptance_failed={exc}")
        print(f"acceptance_evidence={evidence}")
        return 1
    finally:
        session_file.unlink(missing_ok=True)
        _stop(web_proc)
        _stop(api_proc)
        web_log.close()
        api_log.close()


def _prepare_database(name: str, evidence: Path) -> None:
    log_path = evidence / "database.log"
    env = os.environ.copy()
    env["ATLAS_E2E_DATABASE_NAME"] = name
    env["ATLAS_E2E_POSTGRES_HOST"] = "127.0.0.1"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [str(_python()), "-m", "app.scripts.e2e_database"],
            cwd=API,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=240,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"database preparation failed with exit {completed.returncode}")


def _start_api(api_port: int, web_port: int, database: str, log) -> subprocess.Popen:
    env = os.environ.copy()
    env.update({
        "ATLAS_DATABASE_URL": _database_url(database),
        "ATLAS_ENVIRONMENT": "development",
        "ATLAS_PUBLIC_DEMO": "false",
        "ATLAS_PUBLIC_INFERENCE_ENABLED": "false",
        "ATLAS_COOKIE_SECURE": "false",
        "ATLAS_CORS_ORIGINS": f"http://127.0.0.1:{web_port}",
        "ATLAS_BILLING_PROVIDER": "sandbox",
        "ATLAS_STRIPE_SECRET_KEY": "",
        "ATLAS_STRIPE_WEBHOOK_SECRET": "",
        "ATLAS_N8N_LEAD_WEBHOOK_URL": "",
        "ATLAS_EMAIL_MODE": "sandbox",
        "ATLAS_EMAIL_LIVE_ENABLED": "false",
        "ATLAS_CAMPAIGN_LIVE_ENABLED": "false",
        "ATLAS_WHATSAPP_LIVE_ENABLED": "false",
        "ATLAS_SMTP_HOST": "127.0.0.1",
        "ATLAS_SMTP_PORT": "9",
    })
    return subprocess.Popen(
        [str(_python()), "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=API,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def _start_web(web_port: int, api_port: int, log) -> subprocess.Popen:
    env = os.environ.copy()
    env["ATLAS_API_URL"] = f"http://127.0.0.1:{api_port}"
    env["NEXT_DIST_DIR"] = ".next-qa-acceptance"
    return subprocess.Popen(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(web_port)],
        cwd=WEB,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def _run_browser(session_file: Path, evidence: Path) -> dict:
    completed = subprocess.run(
        ["node", str(QA / "functional" / "ui-walk.mjs"), str(session_file)],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
        check=False,
    )
    (evidence / "ui-walk.log").write_text(completed.stdout, encoding="utf-8")
    report = evidence / "ui-walk.json"
    if completed.returncode != 0 or not report.is_file():
        return {"findings": [{
            "id": "QA-UI-RUNNER",
            "severity": "blocker",
            "module": "Overview",
            "workstream": "Workspace interface",
            "title": "The browser acceptance walk did not finish",
            "steps": ["Run the isolated acceptance browser walk."],
            "expected": "The walk writes ui-walk.json.",
            "actual": completed.stdout[-800:],
            "evidence": str(evidence / "ui-walk.log"),
            "acceptance": "The browser walk exits successfully and writes its report.",
        }], "passed": []}
    return json.loads(report.read_text(encoding="utf-8"))


def _integration_findings(walked: dict, evidence: Path) -> None:
    path = evidence / "integration-classification.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    provider = data.get("provider") if isinstance(data.get("provider"), dict) else {}
    assistant = evidence / "assistant-results.json"
    replies = json.loads(assistant.read_text(encoding="utf-8")) if assistant.is_file() else []
    executed = any(row.get("status") == 200 for row in replies)
    if provider.get("llm_ready") and provider.get("llm_provider") not in {None, "double"} and not executed:
        walked["findings"].append({
            "id": "QA-INT-LLM-BADGE",
            "severity": "major",
            "module": "Integrations",
            "workstream": "Integrations and providers",
            "title": "The language-model badge says ready without a completed answer",
            "steps": ["Read provider status.", "Send one assistant message on the same workspace."],
            "expected": "Ready means a completed model response, not only a stored key.",
            "actual": f"Provider {provider.get('llm_provider')} was ready and no assistant message completed.",
            "evidence": str(path),
            "acceptance": "A ready language-model badge is accompanied by one completed assistant reply.",
        })
    if provider.get("embedding_ready") and data.get("document_status") not in {None, "ready"}:
        walked["findings"].append({
            "id": "QA-INT-EMBED-BADGE",
            "severity": "major",
            "module": "Integrations",
            "workstream": "Integrations and providers",
            "title": "Embeddings are marked ready but the acceptance note did not index",
            "steps": ["Read embedding status.", "Upload a small text note.", "Read its status after 90 seconds."],
            "expected": "A ready embedding provider indexes the note.",
            "actual": f"embedding_ready={provider.get('embedding_ready')} document={data.get('document_status')}.",
            "evidence": str(path),
            "acceptance": "When embeddings are ready, a small text upload reaches ready.",
        })


def _write_browser_session(path: Path, web_port: int, evidence: Path, seed) -> None:
    path.write_text(json.dumps({
        "web": f"http://127.0.0.1:{web_port}",
        "adminEmail": str(seed.seed_admin_email),
        "adminPassword": seed.seed_admin_password,
        "evidence": str(evidence),
    }), encoding="utf-8")


def _database_url(database: str) -> str:
    values: dict[str, str] = {}
    env_file = REPO / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip().startswith("POSTGRES_"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    user = quote_plus(os.environ.get("POSTGRES_USER", values.get("POSTGRES_USER", "atlas")))
    password = quote_plus(os.environ.get("POSTGRES_PASSWORD", values.get("POSTGRES_PASSWORD", "atlas")))
    host = "127.0.0.1"
    port = os.environ.get("POSTGRES_PORT", values.get("POSTGRES_PORT", "5432"))
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def _python() -> Path:
    return API / ".venv" / "Scripts" / "python.exe"


def _free_port(start: int) -> int:
    port = start
    while port < start + 20:
        if not _listening(port):
            return port
        port += 1
    raise RuntimeError(f"no free port from {start}")


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_http(url: str, process: subprocess.Popen, log_path: Path, timeout: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            tail = _redact_log(log_path.read_text(encoding="utf-8", errors="replace")[-600:])
            raise RuntimeError(f"process exited before {url} was ready: {tail}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}")


def _shared_health() -> dict[str, str]:
    return {"api": _probe("http://127.0.0.1:8000/api/v1/health"), "web": _probe("http://127.0.0.1:3000/login")}


def _probe(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return str(response.status)
    except Exception as exc:
        return type(exc).__name__


def _redact_log(text: str) -> str:
    return re.sub(r"[a-z][a-z0-9+.-]*://[^\s]+", "[redacted-url]", text, flags=re.IGNORECASE)


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
