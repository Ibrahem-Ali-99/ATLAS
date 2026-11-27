"""Persistent public-inference budgets.

Counters survive a process restart. A reservation is written before the
provider is called. If the ledger cannot be read or written, the call is
refused. The ledger stores token counts, not the visitor's message.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.db.base import Base
from app.domains.assistant.inference_guard import InferenceDecision

logger = structlog.get_logger(__name__)
_LOCK = 88421027


class PublicInferenceControl(Base):
    """One row. An administrator can stop public model calls without a restart."""

    __tablename__ = "public_inference_control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    killed: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PublicInferenceSpend(Base):
    """One reserved or settled public model call for a single organization."""

    __tablename__ = "public_inference_spend"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def public_inference_killed(db: Session | None = None) -> bool:
    session = db or SessionLocal()
    close = db is None
    try:
        row = session.get(PublicInferenceControl, 1)
        return row is not None and row.killed
    except Exception as exc:
        logger.warning("public_inference_control_unreadable", error_type=type(exc).__name__)
        return True
    finally:
        if close:
            session.close()


def set_public_inference_killed(db: Session, killed: bool) -> bool:
    row = db.get(PublicInferenceControl, 1)
    if row is None:
        row = PublicInferenceControl(id=1, killed=killed, updated_at=datetime.now(UTC))
        db.add(row)
    else:
        row.killed = killed
        row.updated_at = datetime.now(UTC)
    db.commit()
    return row.killed


def reserve_public_inference(
    organization_id: uuid.UUID,
    session_key: str,
    message: str,
    *,
    now: datetime | None = None,
) -> InferenceDecision:
    settings = get_settings()
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    estimate_in, estimate_out = _estimate_tokens(message, settings)
    estimate_cost = _cost_micros(estimate_in, estimate_out, settings)
    session = SessionLocal()
    try:
        session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK})
        if public_inference_killed(session):
            session.rollback()
            return InferenceDecision(
                False,
                "public_inference_disabled",
                "Public model replies are disabled",
            )
        denial = _over_budget(
            session,
            settings,
            organization_id,
            session_key,
            moment,
            estimate_in + estimate_out,
            estimate_cost,
        )
        if denial is not None:
            session.rollback()
            return denial
        row = PublicInferenceSpend(
            organization_id=organization_id,
            session_key=session_key[:200],
            status="reserved",
            input_tokens=estimate_in,
            output_tokens=estimate_out,
            cost_micros=estimate_cost,
            created_at=moment,
        )
        session.add(row)
        session.commit()
        return InferenceDecision(True, "allowed", "Allowed", row.id)
    except Exception as exc:
        session.rollback()
        logger.warning("public_inference_budget_failed", error_type=type(exc).__name__)
        return InferenceDecision(
            False,
            "public_inference_unavailable",
            "Public replies are temporarily unavailable",
        )
    finally:
        session.close()


def settle_public_inference(
    reservation_id: uuid.UUID | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    """Replace a reservation with the provider's usage. Missing usage keeps the hold."""

    if reservation_id is None or input_tokens is None or output_tokens is None:
        return
    settings = get_settings()
    prompt = max(0, input_tokens)
    completion = max(0, output_tokens)
    session = SessionLocal()
    try:
        row = session.get(PublicInferenceSpend, reservation_id)
        if row is None:
            return
        row.status = "settled"
        row.input_tokens = prompt
        row.output_tokens = completion
        row.cost_micros = _cost_micros(prompt, completion, settings)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("public_inference_settle_failed", error_type=type(exc).__name__)
    finally:
        session.close()


def void_public_inference(reservation_id: uuid.UUID | None) -> None:
    """Drop a reservation that never became a model call."""

    if reservation_id is None:
        return
    session = SessionLocal()
    try:
        row = session.get(PublicInferenceSpend, reservation_id)
        if row is not None and row.status == "reserved":
            session.delete(row)
            session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("public_inference_void_failed", error_type=type(exc).__name__)
    finally:
        session.close()


def _over_budget(
    session: Session,
    settings: Settings,
    organization_id: uuid.UUID,
    session_key: str,
    moment: datetime,
    incoming_tokens: int,
    incoming_cost: int,
) -> InferenceDecision | None:
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    hour_start = moment - timedelta(seconds=settings.public_inference_window_seconds)
    session_count, session_tokens, _session_cost = _totals(
        session,
        PublicInferenceSpend.organization_id == organization_id,
        PublicInferenceSpend.session_key == session_key[:200],
    )
    if session_count >= settings.public_inference_session_limit:
        return _budget("public_inference_session_budget", "This chat has reached its reply limit")
    if session_tokens + incoming_tokens > settings.public_inference_session_tokens:
        return _budget("public_inference_token_budget", "This chat has reached its token limit")
    hour_count, hour_tokens, _hour_cost = _totals(
        session, PublicInferenceSpend.created_at >= hour_start
    )
    if hour_count >= settings.public_inference_global_limit:
        return _budget(
            "public_inference_global_budget", "Public replies are temporarily unavailable"
        )
    if hour_tokens + incoming_tokens > settings.public_inference_hourly_tokens:
        return _budget(
            "public_inference_token_budget", "Public replies have reached the hourly token limit"
        )
    day_count, day_tokens, _day_cost = _totals(
        session, PublicInferenceSpend.created_at >= day_start
    )
    if day_count >= settings.public_inference_daily_limit:
        return _budget(
            "public_inference_daily_budget", "Public replies have reached the daily limit"
        )
    if day_tokens + incoming_tokens > settings.public_inference_daily_tokens:
        return _budget(
            "public_inference_token_budget", "Public replies have reached the daily token limit"
        )
    month_count, month_tokens, month_cost = _totals(
        session, PublicInferenceSpend.created_at >= month_start
    )
    if month_count >= settings.public_inference_monthly_limit:
        return _budget(
            "public_inference_monthly_budget", "Public replies have reached the monthly limit"
        )
    if month_tokens + incoming_tokens > settings.public_inference_monthly_tokens:
        return _budget(
            "public_inference_token_budget", "Public replies have reached the monthly token limit"
        )
    cap = int(math.ceil(settings.public_inference_monthly_spend_usd * 1_000_000))
    if month_cost + incoming_cost > cap:
        return _budget(
            "public_inference_spend_budget", "Public replies have reached the spending limit"
        )
    return None


def _totals(session: Session, *filters: object) -> tuple[int, int, int]:
    count, tokens, cost = session.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(PublicInferenceSpend.input_tokens + PublicInferenceSpend.output_tokens),
                0,
            ),
            func.coalesce(func.sum(PublicInferenceSpend.cost_micros), 0),
        ).where(*filters)
    ).one()
    return int(count), int(tokens), int(cost)


def _estimate_tokens(message: str, settings: Settings) -> tuple[int, int]:
    characters = min(len(message.strip()), settings.public_inference_max_input_chars)
    # The grounded prompt adds the retrieved passages. Hold that cost before the call.
    incoming = characters // 4 + 1_500
    return incoming, settings.public_inference_max_output_tokens


def _cost_micros(input_tokens: int, output_tokens: int, settings: Settings) -> int:
    usd = (input_tokens / 1_000_000) * settings.public_llm_input_usd_per_million
    usd += (output_tokens / 1_000_000) * settings.public_llm_output_usd_per_million
    return int(math.ceil(usd * 1_000_000))


def _budget(code: str, message: str) -> InferenceDecision:
    return InferenceDecision(False, code, message)
