"""Checks the version-controlled n8n workflows against ATLAS callbacks.

The lead workflow must keep the webhook path ATLAS calls and must forward the
callback URL ATLAS signs. The follow-up workflow must call the follow-up hooks
and must read its signing secret from the environment, not from the file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / "infrastructure" / "n8n"

WORKFLOWS = {
    "ATLAS Lead Processing": WORKFLOW_DIR / "lead-processing.json",
    "ATLAS Follow-up": WORKFLOW_DIR / "follow-up.json",
}

STABLE_IDS = {
    "ATLAS Lead Processing": "c0ffee00-0000-4000-8000-000000000001",
    "ATLAS Follow-up": "c0ffee00-0000-4000-8000-000000000002",
}

LEAD_WEBHOOK_PATH = "atlas-lead"
FOLLOW_UP_CALLBACKS = (
    "/api/v1/hooks/follow-ups",
    "/api/v1/hooks/follow-ups/request",
)


class ContractError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in walk_strings(child)]
    return []


def load_definitions() -> list[dict[str, object]]:
    loaded: list[dict[str, object]] = []
    for name, path in WORKFLOWS.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise ContractError(f"workflow_file:{path.name}")
        workflow = payload[0]
        if workflow.get("name") != name:
            raise ContractError(f"workflow_name:{path.name}")
        validate_definition(workflow)
        loaded.append(workflow)
    return loaded


def validate_definition(workflow: dict[str, object]) -> None:
    name = workflow.get("name")
    strings = walk_strings(workflow)
    joined = "\n".join(strings)
    if name == "ATLAS Lead Processing":
        if LEAD_WEBHOOK_PATH not in strings:
            raise ContractError("lead_webhook_path")
        if not any("callback_url" in item for item in strings):
            raise ContractError("lead_callback")
        if not all(
            required in joined for required in (
                "$env.ATLAS_LEAD_CALLBACK_ORIGINS",
                "'/api/v1/hooks/lead-processed'",
                "destinations.includes(source.callback_url)",
            )
        ):
            raise ContractError("lead_callback_origin")
    elif name == "ATLAS Follow-up":
        for callback in FOLLOW_UP_CALLBACKS:
            if callback not in joined:
                raise ContractError("follow_up_callback")
        if "$env.ATLAS_HOOK_SECRET" not in joined or "$env.ATLAS_HOOK_KEY_ID" not in joined:
            raise ContractError("follow_up_secret_source")
        if "$env.ATLAS_PUBLIC_API_URL" not in joined:
            raise ContractError("follow_up_api_url")
    else:
        raise ContractError("unexpected_workflow")
    if "ATLAS_HOOK_SECRET=" in joined.replace(" ", ""):
        raise ContractError("embedded_secret")


def inactive_copy(workflow: dict[str, object]) -> dict[str, object]:
    name = workflow.get("name")
    if not isinstance(name, str) or name not in STABLE_IDS:
        raise ContractError("unexpected_workflow")
    copied = json.loads(json.dumps(workflow))
    copied["id"] = STABLE_IDS[name]
    copied["active"] = False
    copied.pop("activeVersionId", None)
    return copied


def classify(
    existing: list[dict[str, object]], wanted: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[str]]:
    present: dict[str, int] = {}
    for workflow in existing:
        name = workflow.get("name")
        if isinstance(name, str):
            present[name] = present.get(name, 0) + 1
    for name, count in present.items():
        if name in WORKFLOWS and count > 1:
            raise ContractError(f"duplicate:{name}")
    missing = [
        inactive_copy(workflow)
        for workflow in wanted
        if isinstance(workflow.get("name"), str) and workflow["name"] not in present
    ]
    already = [name for name in WORKFLOWS if name in present]
    return missing, already


def is_published(workflow: dict[str, object]) -> bool:
    return workflow.get("active") is True or bool(workflow.get("activeVersionId"))


def assert_imported(exported: list[dict[str, object]]) -> list[str]:
    names = [workflow.get("name") for workflow in exported]
    active: list[str] = []
    for name in WORKFLOWS:
        if names.count(name) != 1:
            raise ContractError(f"count:{name}")
        workflow = next(item for item in exported if item.get("name") == name)
        validate_definition(workflow)
        if is_published(workflow):
            active.append(name)
    return active
