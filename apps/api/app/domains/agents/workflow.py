import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, interrupt
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from app.core.errors import AppError
from app.domains.agents.events import add_event
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, ApprovalStatus
from app.domains.approvals.service import create_approval, execute_decisions, list_for_run
from app.domains.crm import service as crm
from app.integrations.business_mcp import BusinessTools, TransientToolError
from app.integrations.language import ChatClient

CLASSIFY_SYSTEM = (
    "Return one JSON object with the keys category, contact_name, company_name, "
    "summary, lead_title, and draft_response. Do not include any other text."
)

NODE_NAMES = (
    "load_inquiry",
    "classify",
    "retrieve_knowledge",
    "lookup_customer",
    "qualify",
    "propose",
    "await_approval",
    "execute",
    "record_outcome",
)


def retry_tool_error(exc: Exception) -> bool:
    return isinstance(exc, TransientToolError)


TOOL_RETRY = RetryPolicy(
    initial_interval=0.05,
    backoff_factor=1.0,
    max_interval=0.05,
    max_attempts=3,
    jitter=False,
    retry_on=retry_tool_error,
)


class AgentState(TypedDict, total=False):
    subject: str
    body: str
    inquiry_company_id: str | None
    inquiry_lead_id: str | None
    category: str
    contact_name: str
    company_name: str
    summary: str
    lead_title: str
    draft_response: str
    knowledge: list[dict[str, Any]]
    contact_id: str | None
    contact_company_id: str | None
    existing_lead_id: str | None
    qualification: str
    approval_ids: list[str]
    outcome: str


class Classification(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    contact_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(default="", max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    lead_title: str = Field(min_length=1, max_length=200)
    draft_response: str = Field(min_length=1, max_length=4000)


@dataclass
class RunContext:
    db: Session
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID
    run_id: uuid.UUID
    chat: ChatClient
    tools: BusinessTools


_current: ContextVar[RunContext] = ContextVar("atlas_agent_run")


def bind_run(context: RunContext) -> Token[RunContext]:
    return _current.set(context)


def release_run(token: Token[RunContext]) -> None:
    _current.reset(token)


def build_graph() -> Any:
    # Node functions return a partial state. LangGraph merges it; mypy cannot.
    graph: Any = StateGraph(AgentState)
    graph.add_node("load_inquiry", load_inquiry)
    graph.add_node("classify", classify)
    graph.add_node("retrieve_knowledge", retrieve_knowledge, retry_policy=TOOL_RETRY)
    graph.add_node("lookup_customer", lookup_customer, retry_policy=TOOL_RETRY)
    graph.add_node("qualify", qualify)
    graph.add_node("propose", propose)
    graph.add_node("await_approval", await_approval)
    graph.add_node("execute", execute)
    graph.add_node("record_outcome", record_outcome)
    previous = START
    for name in NODE_NAMES:
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph


def load_inquiry(_state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    inquiry = crm.get_inquiry(ctx.db, ctx.organization_id, run.inquiry_id)
    add_event(ctx.db, run, "load_inquiry", "succeeded", {"inquiry_id": str(inquiry.id)})
    return {
        "subject": inquiry.subject,
        "body": inquiry.body,
        "inquiry_company_id": str(inquiry.company_id) if inquiry.company_id else None,
        "inquiry_lead_id": str(inquiry.lead_id) if inquiry.lead_id else None,
    }


def classify(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    ctx.chat.ensure_configured()
    raw = ctx.chat.complete(CLASSIFY_SYSTEM, f"Subject: {state['subject']}\n\n{state['body']}")
    parsed = _parse_classification(raw)
    add_event(
        ctx.db,
        run,
        "classify",
        "succeeded",
        {"category": parsed.category, "contact_name": parsed.contact_name},
    )
    return parsed.model_dump()


def retrieve_knowledge(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    hits = ctx.tools.search_company_knowledge(f"{state['subject']}\n{state['body']}")
    add_event(
        ctx.db,
        run,
        "retrieve_knowledge",
        "succeeded",
        {"hits": [_hit_summary(hit) for hit in hits]},
    )
    return {"knowledge": hits}


def lookup_customer(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    found = ctx.tools.find_contact(state["contact_name"])
    contact_id = found.get("id") if isinstance(found, dict) else None
    company_id = found.get("company_id") if isinstance(found, dict) else None
    lead_id = found.get("lead_id") if isinstance(found, dict) else None
    if not isinstance(lead_id, str) or not lead_id:
        lead_id = state.get("inquiry_lead_id")
    existing: str | None = None
    if isinstance(lead_id, str) and lead_id:
        lead = ctx.tools.get_lead(lead_id)
        if isinstance(lead.get("id"), str):
            existing = lead["id"]
    add_event(
        ctx.db,
        run,
        "lookup_customer",
        "succeeded",
        {
            "contact_id": contact_id if isinstance(contact_id, str) else None,
            "lead_id": existing,
        },
    )
    return {
        "contact_id": contact_id if isinstance(contact_id, str) else None,
        "contact_company_id": company_id if isinstance(company_id, str) else None,
        "existing_lead_id": existing,
    }


def qualify(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    matched = bool(state.get("contact_id") or state.get("knowledge"))
    qualification = "qualified" if matched else "unqualified"
    run.qualification = qualification
    ctx.db.commit()
    add_event(ctx.db, run, "qualify", "succeeded", {"qualification": qualification})
    return {"qualification": qualification}


def propose(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    existing = list_for_run(ctx.db, ctx.organization_id, ctx.run_id)
    if len(existing) >= 3:
        return {"approval_ids": [str(item.id) for item in existing]}
    present = {item.action_type for item in existing}
    position = max((item.position for item in existing), default=-1) + 1
    lead_status = "qualified" if state.get("qualification") == "qualified" else "unqualified"
    lead_action, lead_payload = _lead_proposal(state, lead_status)
    appointment_start = _appointment_start()
    proposals = [
        (lead_action, lead_payload),
        (
            ActionType.prepare_customer_response,
            {
                "attach_to": "run_lead",
                "lead_id": state.get("existing_lead_id"),
                "to": "inbox@localhost",
                "subject": state["lead_title"][:200],
                "body": state["draft_response"],
            },
        ),
        (
            ActionType.request_appointment,
            {
                "attach_to": "run_lead",
                "lead_id": state.get("existing_lead_id"),
                "body": f"Appointment requested: {state['summary']}"[:4000],
                "starts_at": appointment_start.isoformat(),
                "ends_at": (appointment_start + timedelta(minutes=30)).isoformat(),
            },
        ),
    ]
    created = list(existing)
    for action, payload in proposals:
        if action in present:
            continue
        created.append(
            create_approval(
                ctx.db,
                organization_id=ctx.organization_id,
                run_id=ctx.run_id,
                requested_by=ctx.actor_user_id,
                action_type=action,
                payload=payload,
                position=position,
            )
        )
        position += 1
    run.status = RunStatus.awaiting_approval
    ctx.db.commit()
    add_event(
        ctx.db,
        run,
        "propose",
        "succeeded",
        {"actions": [item.action_type.value for item in created]},
    )
    return {"approval_ids": [str(item.id) for item in created]}


def await_approval(state: AgentState) -> dict[str, Any]:
    """Stop until a person decides. The model has no approval tool."""

    ctx = _current.get()
    run = _run(ctx)
    if _pending(ctx):
        run.status = RunStatus.awaiting_approval
        ctx.db.commit()
        add_event(
            ctx.db,
            run,
            "await_approval",
            "paused",
            {"approval_ids": state.get("approval_ids", [])},
        )
        interrupt({"approval_ids": state.get("approval_ids", [])})
    if _pending(ctx):
        interrupt({"approval_ids": state.get("approval_ids", [])})
    add_event(ctx.db, run, "await_approval", "succeeded", {})
    return {}


def execute(_state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    executed, rejected, failed = execute_decisions(ctx.db, ctx.organization_id, ctx.run_id)
    outcome = f"{executed} executed, {rejected} rejected, {failed} failed"
    add_event(
        ctx.db,
        run,
        "execute",
        "failed" if failed else "succeeded",
        {"executed": executed, "rejected": rejected, "failed": failed},
    )
    if failed:
        raise AppError(409, "agent_action_failed", "An approved action could not be completed")
    return {"outcome": outcome}


def record_outcome(state: AgentState) -> dict[str, Any]:
    ctx = _current.get()
    run = _run(ctx)
    run.status = RunStatus.completed
    run.finished_at = datetime.now(UTC)
    run.error_code = None
    run.error_message = None
    ctx.db.commit()
    add_event(ctx.db, run, "record_outcome", "succeeded", {"outcome": state.get("outcome", "")})
    return {"outcome": state.get("outcome", "")}


def _run(ctx: RunContext) -> AgentRun:
    run = ctx.db.get(AgentRun, ctx.run_id)
    if run is None or run.organization_id != ctx.organization_id:
        raise AppError(404, "not_found", "Resource not found")
    return run


def _pending(ctx: RunContext) -> bool:
    return any(
        item.status == ApprovalStatus.pending
        for item in list_for_run(ctx.db, ctx.organization_id, ctx.run_id)
    )


def _parse_classification(raw: str) -> Classification:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return Classification.model_validate_json(text)
    except ValidationError as exc:
        raise AppError(
            502, "llm_failed", "The language model returned an unexpected response"
        ) from exc


def _lead_proposal(state: AgentState, lead_status: str) -> tuple[ActionType, dict[str, Any]]:
    if state.get("existing_lead_id"):
        return ActionType.update_lead, {
            "lead_id": state["existing_lead_id"],
            "status": lead_status,
            "notes": state["summary"],
        }
    company_id = state.get("contact_company_id") or state.get("inquiry_company_id")
    return ActionType.create_lead, {
        "title": state["lead_title"],
        "status": lead_status,
        "company_id": company_id,
        "contact_id": state.get("contact_id"),
        "source": "agent",
        "notes": state["summary"],
    }


def _appointment_start() -> datetime:
    return (datetime.now(UTC) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)


def _hit_summary(hit: dict[str, Any]) -> dict[str, Any]:
    content = hit.get("content")
    return {
        "document_title": hit.get("document_title"),
        "score": hit.get("score"),
        "excerpt": content[:180] if isinstance(content, str) else "",
    }


def graph_node_names() -> set[str]:
    return set(build_graph().nodes)
