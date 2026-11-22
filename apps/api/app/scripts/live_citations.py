"""One grounded question against the local demo organization.

Prints titles and booleans. Does not print keys, prompts, or the database URL.
It leaves the conversation it creates. It does not delete rows.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.assistant.service import complete_turn, create_conversation, prepare_turn
from app.domains.identity.models import Organization, User
from app.domains.knowledge.models import Document
from app.integrations.language import get_chat_client, get_embedding_client
from app.scripts.seed import SeedSettings

QUESTION = "How many bonded pallets does the acceptance yard store?"


def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.llm_api_key.strip():
        raise SystemExit("live citation check is blocked: the local key is absent")
    seed = SeedSettings()
    email = str(seed.seed_admin_email).lower()
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).where(Organization.slug == "atlas-demo"))
        user = db.scalar(select(User).where(User.email == email))
        if org is None or user is None:
            raise SystemExit("live citation check is blocked: the demo membership is absent")
        titles = list(
            db.scalars(
                select(Document.title).where(
                    Document.organization_id == org.id, Document.status == "ready"
                )
            ).all()
        )
        print("ready_documents", len(titles))
        print("has_cedar", any("cedar" in title.lower() for title in titles))
        chat = get_chat_client()
        embedder = get_embedding_client()
        conversation = create_conversation(db, org.id, user.id, None)
        turn = prepare_turn(db, org.id, user.id, conversation.id, QUESTION, embedder, chat)
        if not turn.needs_model:
            print("model_called", False)
            print("stored_answer", _safe(turn.refusal or ""))
            return
        reply = complete_turn(db, turn, chat)
        answer = reply.message.content
        if "gsk_" in answer.lower():
            raise SystemExit("live citation check stopped: the answer contained key material")
        source_titles = [source.title for source in reply.message.sources]
        print("model_called", True)
        print("llm_provider", settings.llm_provider)
        print("embedding_provider", settings.embedding_provider)
        print("answer_has_42", "42" in answer)
        print("qualified", "could not confirm" in answer.lower())
        print("source_count", len(source_titles))
        print("source_titles", [_safe(title) for title in source_titles])
        print("cedar_cited", any("cedar" in title.lower() for title in source_titles))
        print("answer", _safe(answer))
    except AppError as exc:
        print("citation_error", exc.code)
        raise SystemExit(1) from exc
    finally:
        db.close()


def _safe(value: str) -> str:
    return " ".join(value.split())[:180].encode("ascii", "replace").decode("ascii")


if __name__ == "__main__":
    main()
