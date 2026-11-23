"""Import the ATLAS n8n workflows without activating them.

Re-running the command does not create a second copy. Webhook signing secrets
stay in the n8n environment and are removed from any error output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from n8n_contract import (
    WORKFLOWS,
    ContractError,
    assert_imported,
    classify,
    load_definitions,
)

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "infrastructure" / "compose.staging.yaml"
DEFAULT_ENV = ROOT / "infrastructure" / "staging" / ".env"
FORBIDDEN_PROJECTS = {"atlas", "infrastructure", "titan", "legalstats"}
SECRET_KEYS = {
    "STAGING_SECRET_KEY",
    "STAGING_POSTGRES_PASSWORD",
    "STAGING_N8N_ENCRYPTION_KEY",
    "STAGING_HOOK_SECRET",
    "STAGING_LLM_API_KEY",
    "ATLAS_BOOTSTRAP_PASSWORD",
}
PLACEHOLDERS = ("replace-with", "dev-only", "change-me", "changeme")


class ProvisionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key in SECRET_KEYS:
        secret = env.get(key, "")
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def assert_secrets(env: dict[str, str]) -> None:
    session = env.get("STAGING_SECRET_KEY", "")
    encryption = env.get("STAGING_N8N_ENCRYPTION_KEY", "")
    if len(session) < 32 or any(marker in session.lower() for marker in PLACEHOLDERS):
        raise ProvisionError("weak_session_secret")
    if len(encryption) < 32 or any(marker in encryption.lower() for marker in PLACEHOLDERS):
        raise ProvisionError("weak_n8n_encryption_key")
    hook = env.get("STAGING_HOOK_SECRET", "")
    if hook and (len(hook) < 16 or any(marker in hook.lower() for marker in PLACEHOLDERS)):
        raise ProvisionError("weak_hook_secret")


def compose(
    project: str,
    env_file: Path,
    args: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    if project in FORBIDDEN_PROJECTS:
        raise ProvisionError("protected_project")
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--project-directory",
        str(ROOT / "infrastructure"),
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    result.stdout = redact(result.stdout, env)
    result.stderr = redact(result.stderr, env)
    return result


def parse_export(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    start = text.find("[")
    payload = json.loads(text[start:] if start >= 0 else text)
    if isinstance(payload, dict):
        workflows = payload.get("workflows", [])
    else:
        workflows = payload
    if not isinstance(workflows, list):
        raise ProvisionError("export_unreadable")
    return [item for item in workflows if isinstance(item, dict)]


def export_workflows(project: str, env_file: Path, env: dict[str, str]) -> list[dict[str, object]]:
    remote = "/tmp/atlas-workflow-export.json"
    with tempfile.TemporaryDirectory() as directory:
        local = Path(directory) / "export.json"
        last = ""
        for _attempt in range(8):
            result = compose(
                project,
                env_file,
                [
                    "exec",
                    "-T",
                    "-u",
                    "node",
                    "n8n",
                    "n8n",
                    "export:workflow",
                    "--all",
                    "--output",
                    remote,
                ],
                env,
            )
            if result.returncode == 0:
                copied = compose(project, env_file, ["cp", f"n8n:{remote}", str(local)], env)
                compose(project, env_file, ["exec", "-T", "-u", "node", "n8n", "rm", "-f", remote], env)
                if copied.returncode == 0 and local.is_file():
                    return parse_export(local)
            last = f"{result.stdout}\n{result.stderr}".strip()
            if "No workflows found" in last or "no workflows" in last.lower():
                return []
            time.sleep(2)
        raise ProvisionError(f"export_failed:{last[-400:]}")


def import_workflow(
    project: str, env_file: Path, env: dict[str, str], workflow: dict[str, object]
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        local = Path(directory) / "workflow.json"
        local.write_text(json.dumps([workflow]), encoding="utf-8")
        remote = "/tmp/atlas-workflow-import.json"
        copied = compose(project, env_file, ["cp", str(local), f"n8n:{remote}"], env)
        if copied.returncode != 0:
            raise ProvisionError("import_copy_failed")
        result = compose(
            project,
            env_file,
            ["exec", "-T", "-u", "node", "n8n", "n8n", "import:workflow", "--input", remote],
            env,
        )
        compose(project, env_file, ["exec", "-T", "-u", "node", "n8n", "rm", "-f", remote], env)
        if result.returncode != 0:
            detail = f"{result.stdout}\n{result.stderr}".strip()
            raise ProvisionError(f"import_failed:{detail[-400:]}")


def deactivate(
    project: str, env_file: Path, env: dict[str, str], workflow_id: str
) -> None:
    result = compose(
        project,
        env_file,
        [
            "exec",
            "-T",
            "-u",
            "node",
            "n8n",
            "n8n",
            "update:workflow",
            f"--id={workflow_id}",
            "--active=false",
        ],
        env,
    )
    if result.returncode != 0:
        raise ProvisionError("deactivate_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import inactive ATLAS n8n workflows")
    parser.add_argument("--project", default="atlas-staging")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args(argv)
    if not args.env_file.is_file():
        print("provision_refused reason=missing_env")
        return 2
    env = read_env(args.env_file)
    try:
        assert_secrets(env)
        wanted = load_definitions()
        existing = export_workflows(args.project, args.env_file, env)
        missing, already = classify(existing, wanted)
        imported_names = [str(workflow["name"]) for workflow in missing]
        for workflow in missing:
            import_workflow(args.project, args.env_file, env, workflow)
        exported = export_workflows(args.project, args.env_file, env)
        for workflow in exported:
            name = workflow.get("name")
            workflow_id = workflow.get("id")
            if name in imported_names and workflow.get("active") is True and isinstance(workflow_id, str):
                deactivate(args.project, args.env_file, env, workflow_id)
        exported = export_workflows(args.project, args.env_file, env)
        active = assert_imported(exported)
        still_active = [name for name in active if name in imported_names]
        if still_active:
            raise ProvisionError("imported_active")
    except (ProvisionError, ContractError) as exc:
        reason = exc.reason if isinstance(exc, (ProvisionError, ContractError)) else "failed"
        print(f"provision_refused reason={redact(reason, env)}")
        return 2
    print(
        "provision_ok "
        f"workflows={len(WORKFLOWS)} imported={len(imported_names)} "
        f"existing={len(already)} active={len(active)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
