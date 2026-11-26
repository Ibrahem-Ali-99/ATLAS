"""Exercise module APIs on the isolated workspace and record product defects."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from harness.client import ApiSession, redact

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "sealed" / "bank.json"


def run(session: ApiSession, outsider: ApiSession, evidence: Path) -> dict[str, Any]:
    fixture = json.loads(BANK.read_text(encoding="utf-8"))["fixture"]
    org = session.organization("atlas-demo")
    organization_id = str(org["organization_id"])
    findings: list[dict[str, Any]] = []
    passed: list[str] = []

    before_companies = _total(session, organization_id, "/companies")
    company = _must_create(
        session, organization_id, "/companies",
        {"name": fixture["company"], "industry": fixture["industry"], "origin": "operational"},
        findings, "CRM", "create a company",
    )
    contact = None
    lead = None
    inquiry = None
    if company is not None:
        contact = _must_create(
            session, organization_id, "/contacts",
            {
                "full_name": fixture["contact"],
                "email": fixture["email"],
                "title": fixture["title"],
                "company_id": company["id"],
                "origin": "operational",
            },
            findings, "CRM", "create a contact",
        )
    if contact is not None and company is not None:
        lead = _must_create(
            session, organization_id, "/leads",
            {
                "title": fixture["lead"],
                "status": fixture["lead_status"],
                "company_id": company["id"],
                "contact_id": contact["id"],
                "source": "acceptance",
                "notes": "Night gate overflow asked by the duty manager.",
                "origin": "operational",
            },
            findings, "CRM", "create a lead",
        )
    if lead is not None and company is not None:
        inquiry = _must_create(
            session, organization_id, "/inquiries",
            {
                "subject": fixture["inquiry_subject"],
                "body": fixture["inquiry_body"],
                "company_id": company["id"],
                "lead_id": lead["id"],
                "origin": "operational",
            },
            findings, "CRM", "create an inquiry",
        )

    if company is not None:
        status, page = session.call(
            "GET", organization_id, "/companies", params={"q": fixture["company"]}
        )
        names = [item.get("name") for item in (page.get("items") or [])] if isinstance(page, dict) else []
        if status != 200 or fixture["company"] not in names:
            findings.append(_finding(
                "QA-CRM-SEARCH", "major", "CRM", "CRM and customer operations",
                "Company search does not return a company that was just saved",
                ["Sign in as an administrator.", "Create a company.", "Search companies for that exact name."],
                "The new company is the first matching result.",
                f"Search status {status} returned {names}.",
                "Search returns the saved company after creation without a reload of the database.",
            ))
        else:
            passed.append("crm-search")
        status, updated = session.call(
            "PATCH", organization_id, f"/companies/{company['id']}",
            json_body={"notes": "Acceptance note kept on the company."},
        )
        status_again, persisted = session.call("GET", organization_id, f"/companies/{company['id']}")
        notes = persisted.get("notes") if isinstance(persisted, dict) else None
        if status != 200 or status_again != 200 or notes != "Acceptance note kept on the company.":
            findings.append(_finding(
                "QA-CRM-PERSIST", "blocker", "CRM", "CRM and customer operations",
                "Editing a company does not persist",
                ["Open a saved company.", "Change the notes.", "Load the company again."],
                "The saved notes are returned on the next read.",
                f"Patch status {status}; reload status {status_again}; notes={notes!r}.",
                "A company edit survives a fresh read.",
            ))
        else:
            passed.append("crm-persist")

    denied, denied_body = session.call(
        "POST", organization_id, "/companies",
        json_body={"name": "CSRF probe company", "origin": "operational"},
        csrf=False,
    )
    if denied != 403:
        findings.append(_finding(
            "QA-CRM-CSRF", "blocker", "CRM", "Identity and access",
            "A company can be created without the session CSRF token",
            ["Sign in.", "POST a company without the CSRF header."],
            "The API refuses the write.",
            f"Status {denied}: {redact(denied_body)}.",
            "State-changing CRM requests without the session CSRF token are refused.",
        ))
    else:
        passed.append("crm-csrf")

    if company is not None:
        northwind = outsider.organization("northwind")
        status, body = outsider.call("GET", str(northwind["organization_id"]), f"/companies/{company['id']}")
        if status != 404:
            findings.append(_finding(
                "QA-CRM-TENANT", "blocker", "CRM", "Identity and access",
                "Another organization can read a company it does not own",
                ["Create a company in Atlas Demo.", "Read that company id as the Northwind administrator."],
                "The read is not found.",
                f"Status {status}: {redact(body)}.",
                "A company id from another organization returns not found.",
            ))
        else:
            passed.append("crm-tenant")

    after_companies = _total(session, organization_id, "/companies")
    if company is not None and after_companies != before_companies + 1:
        findings.append(_finding(
            "QA-CRM-COUNT", "major", "CRM", "CRM and customer operations",
            "Creating a company does not change the company total by one",
            ["Record the company total.", "Create one company.", "Record the total again."],
            "The total increases by one.",
            f"Before {before_companies}, after {after_companies}.",
            "The company list total matches the records just written.",
        ))
    else:
        passed.append("crm-count")

    document = _index_document(session, organization_id, fixture, findings)
    if document is not None and document.get("status") == "ready":
        status, hits = session.call(
            "GET", organization_id, "/documents/search", params={"q": "QL-NIGHT-4481"}
        )
        titles = []
        if isinstance(hits, dict):
            titles = [
                str(item.get("document_title") or item.get("title") or "")
                for item in hits.get("items") or []
                if isinstance(item, dict)
            ]
        if status != 200 or not any("quayline" in title.casefold() for title in titles):
            findings.append(_finding(
                "QA-KNOW-SEARCH", "major", "Knowledge", "Knowledge and retrieval",
                "A ready document is not returned for a unique phrase it contains",
                ["Upload the acceptance note.", "Wait until it is ready.", "Search for its account code."],
                "The note is among the search results.",
                f"Search status {status}; titles={titles}.",
                "Search returns the ready document that contains the queried phrase.",
            ))
        else:
            passed.append("knowledge-search")

    inbox_status, inbox = session.call("GET", organization_id, "/inbox")
    if inbox_status != 200:
        findings.append(_finding(
            "QA-INBOX-LIST", "major", "Inbox", "Inbox and communications",
            "The inbox queue does not load",
            ["Sign in and open Inbox."],
            "The queue returns a list, including an empty list.",
            f"Status {inbox_status}: {redact(inbox)}.",
            "The signed-in inbox queue loads for an administrator.",
        ))
    else:
        passed.append("inbox-list")

    workflow_status, workflow = session.call(
        "POST", organization_id, "/workflow-definitions",
        json_body={
            "name": "QA night gate task",
            "slug": "qa-night-gate-task",
            "description": "Acceptance task that is not activated.",
            "definition": {
                "trigger": "manual",
                "actions": [{"type": "create_task", "title": "Review the night gate", "priority": "normal"}],
            },
        },
    )
    if workflow_status != 201 or not isinstance(workflow, dict) or not workflow.get("id"):
        findings.append(_finding(
            "QA-WORK-CREATE", "major", "Workflows", "Workflows and agent execution",
            "A manual workflow cannot be saved",
            ["Sign in as an administrator.", "Save a manual workflow with one task action.", "Do not activate it."],
            "The workflow is stored and returned.",
            f"Status {workflow_status}: {redact(workflow)}.",
            "An administrator can save an inactive manual workflow.",
        ))
    else:
        listed, rows = session.call("GET", organization_id, "/workflow-definitions")
        slugs = [row.get("slug") for row in rows] if isinstance(rows, list) else []
        if listed != 200 or "qa-night-gate-task" not in slugs:
            findings.append(_finding(
                "QA-WORK-PERSIST", "major", "Workflows", "Workflows and agent execution",
                "A saved workflow does not appear in the library",
                ["Save a workflow.", "Load the workflow library."],
                "The new slug is in the library.",
                f"List status {listed}; slugs={slugs}.",
                "The workflow library includes a workflow that was just saved.",
            ))
        else:
            passed.append("workflow-persist")

    campaign_status, campaign = session.call(
        "POST", organization_id, "/campaigns",
        json_body={
            "name": "QA night gate draft",
            "subject": "Night gate hours",
            "body": "Draft only. This acceptance run does not schedule delivery.",
        },
    )
    if campaign_status != 201:
        findings.append(_finding(
            "QA-CAMP-DRAFT", "major", "Campaigns", "Campaigns and communications",
            "A campaign draft cannot be saved",
            ["Create a campaign without a schedule."],
            "The draft is stored and is not delivered.",
            f"Status {campaign_status}: {redact(campaign)}.",
            "An administrator can save a campaign draft without sending it.",
        ))
    else:
        passed.append("campaign-draft")

    analytics_status, analytics = session.call(
        "GET", organization_id, "/analytics", params={"scope": "all", "period": "90d"}
    )
    companies_total = _nested(analytics, "companies_total") if isinstance(analytics, dict) else None
    if analytics_status != 200:
        findings.append(_finding(
            "QA-AN-LOAD", "major", "Analytics", "Analytics and monitoring",
            "Analytics does not load for the full workspace scope",
            ["Open analytics for all records over 90 days."],
            "The snapshot returns.",
            f"Status {analytics_status}: {redact(analytics)}.",
            "Analytics returns a snapshot for the all-records scope.",
        ))
    elif companies_total != after_companies:
        findings.append(_finding(
            "QA-AN-MISMATCH", "major", "Analytics", "Analytics and monitoring",
            "Analytics company total does not match the CRM company list",
            ["Count companies in CRM.", "Open analytics for all records."],
            "Both totals are the same.",
            f"CRM total {after_companies}; analytics companies_total {companies_total}.",
            "The all-records company total equals the CRM company total.",
        ))
    else:
        passed.append("analytics-companies")

    monitor_status, monitor = session.call("GET", organization_id, "/diagnostics")
    if monitor_status != 200:
        findings.append(_finding(
            "QA-MON-LOAD", "major", "Monitoring", "Analytics and monitoring",
            "Monitoring diagnostics do not load",
            ["Open Monitoring as an administrator."],
            "Diagnostics return.",
            f"Status {monitor_status}: {redact(monitor)}.",
            "Diagnostics load for an administrator.",
        ))
    else:
        passed.append("monitoring")

    billing_status, billing = session.call("GET", organization_id, "/billing")
    mode = billing.get("mode") if isinstance(billing, dict) else None
    if billing_status != 200 or mode != "sandbox":
        findings.append(_finding(
            "QA-BILL-MODE", "blocker", "Billing", "Billing and settings",
            "The isolated acceptance process is not held in sandbox billing",
            ["Open billing on the acceptance process. Do not start checkout."],
            "Billing mode is sandbox and checkout is not sent to Stripe.",
            f"Status {billing_status}; mode={mode!r}.",
            "Acceptance never runs with a live billing provider.",
        ))
    else:
        passed.append("billing-sandbox")

    provider_status, provider = session.call("GET", organization_id, "/provider-status")
    integrations_status, integrations = session.call("GET", organization_id, "/integration-configs")
    calendar_status, calendar = session.call("GET", organization_id, "/calendar/google")
    transport_status, transport = session.call("GET", organization_id, "/campaign-transport")
    classification = {
        "provider_status": provider_status,
        "provider": redact(provider),
        "integrations_status": integrations_status,
        "integrations": redact(integrations),
        "calendar_status": calendar_status,
        "calendar": redact(calendar),
        "transport_status": transport_status,
        "transport": redact(transport),
        "billing_mode": mode,
        "document_status": None if document is None else document.get("status"),
    }
    (evidence / "integration-classification.json").write_text(
        json.dumps(classification, indent=2, default=str), encoding="utf-8"
    )
    if isinstance(provider, dict) and provider.get("llm_ready") and provider.get("llm_provider") == "groq":
        passed.append("provider-badge-groq-configured")
    if isinstance(calendar, dict) and calendar.get("connected") and not calendar.get("available"):
        findings.append(_finding(
            "QA-INT-CAL", "major", "Integrations", "Integrations and providers",
            "Calendar reports a connection that the deployment cannot use",
            ["Read the Google Calendar connection on a fresh workspace."],
            "A connection is reported only when the workspace grant and the deployment client both exist.",
            redact(calendar),
            "Calendar connection status matches a stored grant and a configured client.",
        ))

    members_status, members = session.call("GET", organization_id, "/members")
    if members_status != 200 or not isinstance(members, list) or not members:
        findings.append(_finding(
            "QA-SET-MEMBERS", "major", "Settings", "Billing and settings",
            "Workspace members do not load",
            ["Open settings as an administrator."],
            "The member list includes the signed-in administrator.",
            f"Status {members_status}: {redact(members)}.",
            "Settings shows the members of the current organization.",
        ))
    else:
        passed.append("settings-members")

    approvals_status, approvals = session.call("GET", organization_id, "/approvals")
    runs_status, runs = session.call("GET", organization_id, "/agent-runs")
    if approvals_status != 200 or runs_status != 200:
        findings.append(_finding(
            "QA-QUEUE-LOAD", "major", "Approvals", "Workflows and agent execution",
            "Approvals or agent runs do not load",
            ["Open Approvals and Agent Runs."],
            "Both lists return, including when empty.",
            f"Approvals {approvals_status}; runs {runs_status}.",
            "Both queues load for an administrator.",
        ))
    else:
        passed.append("queues")

    context = {
        "organization_id": organization_id,
        "company_count": after_companies,
        "company_id": None if company is None else company.get("id"),
        "inquiry_id": None if inquiry is None else inquiry.get("id"),
        "document_status": None if document is None else document.get("status"),
        "workflow_id": workflow.get("id") if isinstance(workflow, dict) else None,
        "campaign_id": campaign.get("id") if isinstance(campaign, dict) else None,
    }
    return {"findings": findings, "passed": passed, "context": context, "approvals": approvals, "runs": runs}


def finish_agent(session: ApiSession, staff: ApiSession, context: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    inquiry_id = context.get("inquiry_id")
    organization_id = context["organization_id"]
    if not inquiry_id:
        return findings
    status, run = session.call(
        "POST", organization_id, "/agent-runs", json_body={"inquiry_id": inquiry_id}
    )
    if status not in {200, 201} or not isinstance(run, dict):
        findings.append(_finding(
            "QA-AGENT-START", "major", "Agent Runs", "Workflows and agent execution",
            "An agent run cannot be started from a saved inquiry",
            ["Create an inquiry.", "Start an agent run for it.", "Do not execute a send or a booking."],
            "The run is stored and reaches a visible status.",
            f"Status {status}: {redact(run)}.",
            "Starting a run from an inquiry returns a stored run without sending a message.",
        ))
        return findings
    record = run.get("run") if isinstance(run.get("run"), dict) else run
    approvals = run.get("approvals") if isinstance(run.get("approvals"), list) else []
    pending = [
        item for item in approvals
        if isinstance(item, dict) and item.get("status") in {"pending", "awaiting_approval", None}
    ]
    if staff is not None and pending:
        approval_id = pending[0].get("id")
        denied, denied_body = staff.call(
            "POST", organization_id, f"/approvals/{approval_id}/approve", json_body={}
        )
        if denied != 403:
            findings.append(_finding(
                "QA-APPR-STAFF", "blocker", "Approvals", "Identity and access",
                "A staff member can approve an agent proposal",
                ["Start a run that creates a proposal.", "Approve it as a staff member."],
                "The approval is refused.",
                f"Status {denied}: {redact(denied_body)}.",
                "Only an administrator can approve a proposal.",
            ))
    for item in approvals:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("status") not in {None, "pending"}:
            continue
        session.call("POST", organization_id, f"/approvals/{item['id']}/reject", json_body={})
    context["agent_run_status"] = record.get("status")
    context["agent_run_id"] = record.get("id")
    return findings


def _index_document(
    session: ApiSession,
    organization_id: str,
    fixture: dict[str, str],
    findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    status, created = session.call(
        "POST", organization_id, "/documents",
        files={"file": (fixture["document_name"], fixture["document_text"].encode(), "text/plain")},
        data={"origin": "operational"},
    )
    if status != 201 or not isinstance(created, dict) or not created.get("id"):
        findings.append(_finding(
            "QA-KNOW-UPLOAD", "blocker", "Knowledge", "Knowledge and retrieval",
            "A text note cannot be uploaded",
            ["Upload a small text file from Knowledge."],
            "The document is accepted and enters processing.",
            f"Status {status}: {redact(created)}.",
            "A plain-text operating note is accepted for indexing.",
        ))
        return None
    document_id = created["id"]
    observed = created.get("status")
    deadline = time.time() + 90
    while time.time() < deadline and observed in {None, "pending", "processing"}:
        time.sleep(2)
        read_status, body = session.call("GET", organization_id, f"/documents/{document_id}")
        if read_status == 200 and isinstance(body, dict):
            observed = body.get("status")
            created = body
    if observed != "ready":
        findings.append(_finding(
            "QA-KNOW-INDEX", "blocker", "Knowledge", "Knowledge and retrieval",
            "An uploaded note does not become ready",
            ["Upload a text note.", "Wait up to 90 seconds.", "Read the document status."],
            "The document reaches ready and can be retrieved.",
            f"Last status {observed!r}: {redact(created)}.",
            "A small text upload reaches ready without a manual retry.",
        ))
    return created


def _must_create(
    session: ApiSession,
    organization_id: str,
    path: str,
    body: dict[str, Any],
    findings: list[dict[str, Any]],
    module: str,
    action: str,
) -> dict[str, Any] | None:
    status, created = session.call("POST", organization_id, path, json_body=body)
    if status != 201 or not isinstance(created, dict) or not created.get("id"):
        findings.append(_finding(
            f"QA-CREATE-{path.strip('/').upper()}", "blocker", module, "CRM and customer operations",
            f"Cannot {action}",
            [f"Submit the {path.strip('/')} form with the acceptance values."],
            "The record is saved and returned.",
            f"Status {status}: {redact(created)}.",
            f"An administrator can {action} and receive the stored record.",
        ))
        return None
    return created


def _total(session: ApiSession, organization_id: str, path: str) -> int | None:
    status, body = session.call("GET", organization_id, path, params={"page_size": 1})
    if status == 200 and isinstance(body, dict) and isinstance(body.get("total"), int):
        return body["total"]
    return None


def _nested(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = _nested(item, key)
            if found is not None:
                return found
    return None


def _finding(
    identifier: str,
    severity: str,
    module: str,
    workstream: str,
    title: str,
    steps: list[str],
    expected: str,
    actual: Any,
    acceptance: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "severity": severity,
        "module": module,
        "workstream": workstream,
        "title": title,
        "steps": steps,
        "expected": expected,
        "actual": actual if isinstance(actual, str) else json.dumps(actual, default=str),
        "evidence": "",
        "acceptance": acceptance,
    }
