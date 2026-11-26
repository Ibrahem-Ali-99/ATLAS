"""Black-box assistant evaluation. Prompts stay in the sealed bank."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.client import ApiSession, redact
from harness.score import score_reply

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "sealed" / "bank.json"


def run(
    admin: ApiSession,
    staff: ApiSession,
    evidence: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    organization_id = context["organization_id"]
    actors = {"admin": admin, "staff": staff}
    other_names = _other_organization_names(admin, organization_id)
    company_count = context.get("company_count")
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for case in bank["cases"]:
        actor = actors[case.get("actor", "admin")]
        email_before = _email_count(actor, organization_id)
        status, conversation = actor.call(
            "POST", organization_id, "/conversations",
            json_body={"title": f"acceptance {case['id']}"},
        )
        if status != 201 or not isinstance(conversation, dict):
            results.append({"id": case["id"], "category": case["category"], "failures": [f"conversation {status}"]})
            continue
        reply: dict[str, Any] | None = None
        reply_status = 0
        for turn in case["turns"]:
            reply_status, body = actor.call(
                "POST", organization_id, f"/conversations/{conversation['id']}/messages",
                json_body={"content": turn},
            )
            reply = body if isinstance(body, dict) else {"message": {"content": str(body)}}
            if reply_status != 200:
                break
        failures = [f"message status {reply_status}: {redact(reply)}"] if reply_status != 200 or reply is None else score_reply(
            reply,
            case.get("expect") or {},
            company_count=company_count if isinstance(company_count, int) else None,
            other_organization_names=other_names,
        )
        if (case.get("expect") or {}).get("unchanged_email_count"):
            email_after = _email_count(actor, organization_id)
            if email_before is not None and email_after is not None and email_after != email_before:
                failures.append(f"email activity changed from {email_before} to {email_after}")
        message = (reply or {}).get("message") if isinstance(reply, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        results.append({
            "id": case["id"],
            "category": case["category"],
            "status": reply_status,
            "document_search": None if not isinstance(reply, dict) else reply.get("document_search"),
            "failures": failures,
            "excerpt": str(content)[:500],
        })
    (evidence / "assistant-results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    failed = [row for row in results if row["failures"]]
    if failed:
        by_category: dict[str, list[str]] = {}
        for row in failed:
            by_category.setdefault(row["category"], []).append(row["id"])
        findings.append({
            "id": "QA-ASSIST-USEFUL",
            "severity": "blocker" if len(failed) >= 5 else "major",
            "module": "Assistant",
            "workstream": "Intelligent Assistant",
            "title": "Assistant replies are not consistently useful, accurate, or grounded",
            "steps": [
                "Prepare the isolated acceptance workspace.",
                "Run the sealed black-box suite without opening the bank in the assistant implementation.",
                "Score each case id recorded in assistant-results.json.",
            ],
            "expected": "Each sealed case is relevant, accurate, complete for the workspace records, and does not claim a send, booking, or payment.",
            "actual": json.dumps(
                [{"id": row["id"], "failures": row["failures"], "excerpt": row["excerpt"]} for row in failed],
                indent=2,
            ),
            "evidence": str(evidence / "assistant-results.json"),
            "acceptance": "Re-running the sealed suite reports no failed case ids.",
            "categories": by_category,
        })
    return {"findings": findings, "results": results, "failed": len(failed), "total": len(results)}


def _email_count(session: ApiSession, organization_id: str) -> int | None:
    status, body = session.call("GET", organization_id, "/email-activity")
    if status == 200 and isinstance(body, list):
        return len(body)
    return None


def _other_organization_names(admin: ApiSession, atlas_id: str) -> list[str]:
    northwind = admin.organization("northwind")
    status, page = admin.call("GET", str(northwind["organization_id"]), "/companies", params={"page_size": 100})
    if status != 200 or not isinstance(page, dict):
        return []
    outsider_names = {item.get("name") for item in page.get("items") or [] if isinstance(item, dict)}
    status, own = admin.call("GET", atlas_id, "/companies", params={"page_size": 100})
    own_names = set()
    if status == 200 and isinstance(own, dict):
        own_names = {item.get("name") for item in own.get("items") or [] if isinstance(item, dict)}
    return sorted(name for name in outsider_names - own_names if isinstance(name, str))
