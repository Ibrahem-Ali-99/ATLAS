import importlib.util

import pytest

from tests.bootstrap import REPO_ROOT

_PATH = REPO_ROOT / "infrastructure" / "staging" / "n8n_contract.py"
_SPEC = importlib.util.spec_from_file_location("n8n_contract", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
n8n_contract = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(n8n_contract)


def test_versioned_workflows_match_atlas_callbacks() -> None:
    definitions = n8n_contract.load_definitions()
    assert [item["name"] for item in definitions] == [
        "ATLAS Lead Processing",
        "ATLAS Follow-up",
    ]
    lead_source = (
        REPO_ROOT / "apps" / "api" / "app" / "domains" / "automation" / "workflows.py"
    ).read_text(encoding="utf-8")
    assert "/api/v1/hooks/lead-processed" in lead_source
    for workflow in definitions:
        assert workflow["active"] is False
        n8n_contract.validate_definition(workflow)


def test_import_plan_is_idempotent_and_inactive() -> None:
    wanted = n8n_contract.load_definitions()
    missing, already = n8n_contract.classify([], wanted)
    assert already == []
    assert [item["active"] for item in missing] == [False, False]
    exported = [
        {
            "name": item["name"],
            "active": False,
            "nodes": item["nodes"],
            "connections": item["connections"],
        }
        for item in missing
    ]
    assert n8n_contract.assert_imported(exported) == []

    again, present = n8n_contract.classify(exported, wanted)
    assert again == []
    assert present == ["ATLAS Lead Processing", "ATLAS Follow-up"]


def test_duplicate_workflows_are_refused() -> None:
    wanted = n8n_contract.load_definitions()
    duplicated = [wanted[0], dict(wanted[0])]
    with pytest.raises(n8n_contract.ContractError, match="duplicate"):
        n8n_contract.classify(duplicated, wanted)


def test_staging_compose_keeps_internal_services_private() -> None:
    compose = (REPO_ROOT / "infrastructure" / "compose.staging.yaml").read_text(encoding="utf-8")
    caddy = (REPO_ROOT / "infrastructure" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert compose.count("\n    ports:\n") == 1
    for published in ("5432:5432", "5678:5678", "11434:11434", "8025:8025", "8000:8000"):
        assert published not in compose
    assert "SEED_" not in compose
    assert 'ATLAS_COOKIE_SECURE: "true"' in compose
    assert 'ATLAS_PUBLIC_DEMO: "false"' in compose
    assert "nomic-embed-text:v1.5" in compose
    assert "driver: nvidia" not in compose
    gpu = (REPO_ROOT / "infrastructure" / "compose.gpu.yaml").read_text(encoding="utf-8")
    assert "driver: nvidia" in gpu
    assert "capabilities: [gpu]" in gpu
    assert "reverse_proxy api:8000" in caddy
    assert "reverse_proxy web:3000" in caddy
    for private in ("n8n", "mailpit", "postgres", "ollama", "5678"):
        assert private not in caddy


def test_workflow_files_do_not_embed_a_signing_secret() -> None:
    for path in (REPO_ROOT / "infrastructure" / "n8n").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "ATLAS_HOOK_SECRET=" not in text.replace(" ", "")
        assert "replace-with" not in text
