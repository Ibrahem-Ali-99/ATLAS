"""Opt-in check of the business assistant against a populated Harbor workspace.

Uses the configured chat model (Groq when ATLAS_LLM_PROVIDER=groq) and the
configured embedding model (Ollama when ATLAS_EMBEDDING_PROVIDER=ollama).
Prints tool names and pass/fail lines only. Does not print keys or prompts.
Leaves the conversation it creates.
"""

from __future__ import annotations

import re
import time

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.assistant.executions import steps_for_execution
from app.domains.assistant.models import AssistantExecution
from app.domains.assistant.service import complete_turn, create_conversation, prepare_turn
from app.domains.crm.models import Company
from app.domains.identity.models import Membership, MembershipRole, Organization, User
from app.integrations.language import get_chat_client, get_embedding_client


def main() -> None:
    settings = get_settings()
    if settings.llm_provider == "double" or not settings.llm_api_key.strip():
        raise SystemExit("business assistant check is blocked: a live chat model is not configured")
    db = _open_database()
    try:
        organization, user = _harbor(db)
        chat = get_chat_client(db, organization.id)
        embedder = get_embedding_client(db, organization.id)
        conversation = create_conversation(db, organization.id, user.id, "Business assistant check")
        companies = list(
            db.scalars(
                select(Company.name).where(Company.organization_id == organization.id).limit(3)
            ).all()
        )
        print("organization", organization.slug)
        print("chat_provider", settings.llm_provider)
        print("embedding_provider", settings.embedding_provider)
        print("sample_company", companies[0] if companies else "none")
        checks = [
            ("customers", "Who are our customers?", "list_companies", companies[:1]),
            ("employees", "What are the employee names?", "list_members", [user.full_name]),
            ("leads", "Which leads should I prioritize?", "list_leads", []),
            ("analytics", "How is the business doing?", "business_analytics", []),
            ("knowledge", "What does the bonded warehousing note say?", "search_knowledge", []),
            ("follow_up", "Tell me more about that.", None, []),
            (
                "appointment",
                "Request an appointment for the first open lead",
                "propose_appointment",
                [],
            ),
            ("workflows", "Which workflow runs failed?", "list_workflow_runs", []),
        ]
        for name, question, tool, expected in checks:
            turn = prepare_turn(
                db, organization.id, user.id, conversation.id, question, embedder, chat
            )
            reply = _complete(db, turn, chat)
            answer = reply.message.content
            if "gsk_" in answer:
                raise SystemExit("business assistant check stopped: key material in the answer")
            execution = db.scalar(
                select(AssistantExecution)
                .where(AssistantExecution.conversation_id == conversation.id)
                .order_by(AssistantExecution.started_at.desc())
            )
            tools = [] if execution is None else list(execution.selected_tools)
            steps = [] if execution is None else steps_for_execution(db, execution.id)
            failed = [step.tool_name for step in steps if step.status == "failed"]
            useful = bool(answer.strip()) and "Shortage claims" not in answer
            if name == "customers" and companies:
                useful = useful and any(company in answer for company in companies)
            if name == "employees":
                useful = useful and user.full_name in answer
            if name == "leads":
                useful = useful and answer.lower().count(" is ") >= 2
            if name == "analytics":
                useful = (
                    useful
                    and not re.search(r"\b1 companies\b", answer)
                    and not re.search(r"\b1 leads\b", answer)
                )
            if name == "appointment":
                useful = useful and "Proposed appointment" in answer and "No lead" not in answer
            tool_ok = tool is None or tool in tools
            print(
                name,
                "pass" if useful and tool_ok and not failed else "fail",
                "tools",
                ",".join(tools) or "none",
                "chars",
                len(answer),
            )
            if expected and not any(item and item in answer for item in expected):
                print(name, "missing_expected_text")
    finally:
        db.close()


def _complete(db: Session, turn: object, chat: object) -> object:
    for attempt in range(3):
        try:
            return complete_turn(db, turn, chat)  # type: ignore[arg-type]
        except AppError as exc:
            if exc.code != "llm_rate_limited" or attempt == 2:
                raise
            time.sleep(20)
    raise AppError(429, "llm_rate_limited", "The language model rate limit was reached")


def _open_database() -> Session:
    current = SessionLocal()
    if _find_harbor(current) is not None:
        return current
    current.close()
    settings = get_settings()
    url = settings.database_url.rsplit("/", 1)[0] + "/atlas_harbor"
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise SystemExit(
            "business assistant check is blocked: no Harbor workspace is stored"
        ) from exc
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return factory()


def _find_harbor(db: Session) -> Organization | None:
    return db.scalar(
        select(Organization)
        .where(Organization.name.ilike("%harbor%"), Organization.slug.not_like("harbor-visitor-%"))
        .order_by(Organization.created_at.asc())
    )


def _harbor(db: Session) -> tuple[Organization, User]:
    organization = _find_harbor(db)
    if organization is None:
        raise SystemExit("business assistant check is blocked: no Harbor workspace is stored")
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization.id,
            Membership.role == MembershipRole.admin,
        )
    )
    if membership is None:
        raise SystemExit("business assistant check is blocked: Harbor has no administrator")
    user = db.get(User, membership.user_id)
    if user is None:
        raise SystemExit("business assistant check is blocked: the Harbor administrator is missing")
    return organization, user


if __name__ == "__main__":
    main()
