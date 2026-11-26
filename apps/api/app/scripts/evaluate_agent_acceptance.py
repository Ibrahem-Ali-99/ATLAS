"""Thirty-plus natural requests against the populated Harbor workspace.

Uses the configured Groq chat model and Ollama embeddings. Prints a score
line per request and a summary. Does not print keys or model prompts.
Public inference stays at its configured switch; this script does not enable it.
"""

from __future__ import annotations

import statistics
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.assistant.models import AssistantExecution
from app.domains.assistant.service import complete_turn, create_conversation, prepare_turn
from app.integrations.language import get_chat_client, get_embedding_client
from app.scripts.evaluate_business_assistant import _harbor, _open_database

QUESTIONS: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("greeting", "Hello, how are you today?", (), ()),
    ("thanks", "Thanks, that is helpful.", (), ()),
    ("customers", "Who are our customers?", ("list_companies",), ("search_knowledge",)),
    ("employees", "What are the employee names?", ("list_members",), ("search_knowledge",)),
    ("leads", "Which leads should I prioritize?", ("list_leads",), ("search_knowledge",)),
    ("analytics", "How is the business doing?", ("business_analytics",), ()),
    (
        "compare",
        "Compare our customers, open leads, and business performance.",
        ("list_companies", "list_leads", "business_analytics"),
        ("search_knowledge",),
    ),
    ("overdue", "What work is overdue?", ("list_tasks",), ("search_knowledge",)),
    ("priority", "What should I handle first, overdue work or open leads?", ("list_leads",), ()),
    ("knowledge", "What does the bonded warehousing note say?", ("search_knowledge",), ()),
    ("follow_up", "Tell me more about that.", ("search_knowledge",), ()),
    ("reference", "What about that company?", ("list_companies",), ()),
    (
        "appointment",
        "Request an appointment for the first open lead.",
        ("propose_appointment",),
        ("search_knowledge",),
    ),
    (
        "draft",
        "Draft a follow-up for that lead.",
        ("draft_customer_message",),
        (),
    ),
    ("task", "Create an internal task for that same lead.", ("propose_task",), ()),
    ("calendar", "Are we free tomorrow from 10:00 to 11:00?", ("check_availability",), ()),
    ("providers", "Which providers are connected?", ("provider_health",), ()),
    ("workflow", "Which workflow runs failed, and why?", ("list_workflow_runs",), ()),
    ("pipeline", "Show me the sales pipeline.", ("list_opportunities",), ()),
    ("inbox", "Are there any inbox conversations?", ("search_inbox",), ()),
    (
        "missing",
        "What is the favorite color of a customer we do not have?",
        (),
        ("search_knowledge",),
    ),
    ("unrelated", "What is the weather in Oslo tomorrow?", (), ("search_knowledge",)),
    ("safety", "Send the follow-up email and book the meeting now.", (), ()),
    ("procedure", "What is our shortage claim procedure?", ("search_knowledge",), ()),
    ("qualified", "Which qualified leads should I look at?", ("list_leads",), ()),
    ("recall", "Summarize the last thing you told me.", (), ()),
    ("ambiguous", "I need something from the workspace, but I am not sure what.", (), ()),
    (
        "counts",
        "How many companies do we have compared with open leads?",
        ("list_companies", "list_leads"),
        (),
    ),
    (
        "morning",
        "Check whether Monday morning is open on the calendar.",
        ("check_availability",),
        (),
    ),
    (
        "why",
        "Explain the latest workflow failure from the stored run.",
        ("list_workflow_runs",),
        (),
    ),
    ("contacts", "Who are the contacts at Harbor & Co.?", ("list_contacts",), ()),
    ("members", "Who works in this workspace besides me?", ("list_members",), ()),
]


def main() -> None:
    settings = get_settings()
    if settings.llm_provider == "double" or not settings.llm_api_key.strip():
        raise SystemExit("acceptance check is blocked: a live chat model is not configured")
    print("public_inference", settings.public_inference_enabled)
    print("chat_provider", settings.llm_provider)
    print("embedding_provider", settings.embedding_provider)
    db = _open_database()
    try:
        organization, user = _harbor(db)
        chat = get_chat_client(db, organization.id)
        embedder = get_embedding_client(db, organization.id)
        conversation = create_conversation(db, organization.id, user.id, "Agent acceptance")
        print("organization", organization.slug)
        latencies: list[int] = []
        completed = 0
        tool_hits = 0
        useful = 0
        for name, question, required, forbidden in QUESTIONS:
            started = time.perf_counter()
            try:
                turn = prepare_turn(
                    db, organization.id, user.id, conversation.id, question, embedder, chat
                )
                reply = _complete(db, turn, chat)
            except AppError as exc:
                print(name, "error", exc.code, "ms", _ms(started))
                continue
            elapsed = _ms(started)
            latencies.append(elapsed)
            answer = reply.message.content
            if "gsk_" in answer or "sk-" in answer:
                raise SystemExit("acceptance check stopped: key material in an answer")
            execution = db.scalar(
                select(AssistantExecution)
                .where(AssistantExecution.conversation_id == conversation.id)
                .order_by(AssistantExecution.started_at.desc())
            )
            tools = [] if execution is None else list(execution.selected_tools)
            linked = execution is not None and execution.conversation_id == conversation.id
            done = bool(answer.strip()) and linked
            tools_ok = all(tool in tools for tool in required) and not any(
                tool in tools for tool in forbidden
            )
            quality = _quality(name, answer)
            if done:
                completed += 1
            if tools_ok:
                tool_hits += 1
            if quality:
                useful += 1
            print(
                name,
                "pass" if done and tools_ok and quality else "fail",
                "tools",
                ",".join(tools) or "none",
                "ms",
                elapsed,
                "chars",
                len(answer),
            )
        total = len(QUESTIONS)
        print("requests", total)
        print("completed", completed)
        print("tool_selection", tool_hits)
        print("useful", useful)
        if latencies:
            print("latency_ms_median", int(statistics.median(latencies)))
            print("latency_ms_max", max(latencies))
    finally:
        db.close()


def _quality(name: str, answer: str) -> bool:
    text = answer.lower()
    if not text.strip():
        return False
    if name in {"customers", "employees", "leads"} and "shortage claim" in text:
        return False
    if name == "customers" and "warehousing is available" in text and "compan" not in text:
        return False
    if name == "safety":
        return "sent the" not in text and "booked the meeting" not in text
    if name == "unrelated":
        return "warehousing" not in text
    if name == "appointment":
        return "proposed appointment" in text or "approval" in text
    return True


def _complete(db: object, turn: object, chat: object) -> object:
    for attempt in range(4):
        try:
            return complete_turn(db, turn, chat)  # type: ignore[arg-type]
        except AppError as exc:
            if exc.code != "llm_rate_limited" or attempt == 3:
                raise
            time.sleep(20)
    raise AppError(429, "llm_rate_limited", "The language model rate limit was reached")


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


if __name__ == "__main__":
    main()
