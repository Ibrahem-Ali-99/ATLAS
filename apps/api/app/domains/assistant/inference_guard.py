"""Budgets for public model calls.

The switch is off unless ATLAS_PUBLIC_INFERENCE_ENABLED is set, and a paid
Groq call also requires ATLAS_PUBLIC_LLM_AUTHORIZED. A signed-in workspace
that is not a visitor organization does not use this guard. Persistent
limits are checked when the caller asks to persist. Until the paid path is
authorized, the visitor stays on the deterministic stand-in.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.assistant.routing import is_prompt_injection

_URLS = re.compile(r"https?://", re.IGNORECASE)
_LOCK = threading.Lock()
_SESSION_TIMES: dict[str, list[float]] = {}
_GLOBAL_TIMES: list[float] = []
_IN_FLIGHT = 0

DETERMINISTIC_FALLBACK = (
    "Deterministic fallback: the live model did not answer. "
    "A person should review this chat. This sentence was not produced by the model."
)


@dataclass(frozen=True)
class InferenceDecision:
    allowed: bool
    code: str
    message: str
    reservation_id: uuid.UUID | None = None


def reset_public_inference() -> None:
    global _IN_FLIGHT
    with _LOCK:
        _SESSION_TIMES.clear()
        _GLOBAL_TIMES.clear()
        _IN_FLIGHT = 0


def assess_public_inference(
    session_key: str,
    text: str,
    *,
    now: float | None = None,
    hold_slot: bool = False,
    organization_id: uuid.UUID | None = None,
    persist: bool = False,
) -> InferenceDecision:
    settings = get_settings()
    if not settings.public_inference_enabled:
        return InferenceDecision(
            False,
            "public_inference_disabled",
            "Public model replies are disabled",
        )
    cleaned = text.strip()
    if is_prompt_injection(cleaned):
        return InferenceDecision(False, "public_inference_rejected", "That message was rejected")
    repetitive = bool(cleaned) and len(set(cleaned)) == 1 and len(cleaned) > 40
    if "\x00" in cleaned or repetitive:
        return InferenceDecision(False, "public_inference_rejected", "That message was rejected")
    if len(_URLS.findall(cleaned)) > 3:
        return InferenceDecision(False, "public_inference_rejected", "That message was rejected")
    if len(cleaned) > settings.public_inference_max_input_chars:
        return InferenceDecision(
            False,
            "public_inference_input_limited",
            "That message is too long for a public reply",
        )
    reservation_id: uuid.UUID | None = None
    if persist:
        if organization_id is None:
            return InferenceDecision(
                False,
                "public_inference_unavailable",
                "Public replies are temporarily unavailable",
            )
        from app.domains.assistant.public_budget import reserve_public_inference

        reserved = reserve_public_inference(organization_id, session_key, cleaned)
        if not reserved.allowed:
            return reserved
        reservation_id = reserved.reservation_id
    moment = time.monotonic() if now is None else now
    denied = _claim_memory(session_key, moment, hold_slot)
    if denied is not None:
        if reservation_id is not None:
            from app.domains.assistant.public_budget import void_public_inference

            void_public_inference(reservation_id)
        return denied
    return InferenceDecision(True, "allowed", "Allowed", reservation_id)


def _claim_memory(session_key: str, moment: float, hold_slot: bool) -> InferenceDecision | None:
    settings = get_settings()
    window = settings.public_inference_window_seconds
    global _IN_FLIGHT
    with _LOCK:
        _trim(_GLOBAL_TIMES, moment, window)
        session_times = _SESSION_TIMES.setdefault(session_key, [])
        _trim(session_times, moment, window)
        if (
            session_times
            and moment - session_times[-1] < settings.public_inference_min_interval_seconds
        ):
            return InferenceDecision(
                False,
                "public_inference_rate_limited",
                "Wait before sending another message",
            )
        if len(session_times) >= settings.public_inference_session_limit:
            return InferenceDecision(
                False,
                "public_inference_session_budget",
                "This chat has reached its reply limit",
            )
        if len(_GLOBAL_TIMES) >= settings.public_inference_global_limit:
            return InferenceDecision(
                False,
                "public_inference_global_budget",
                "Public replies are temporarily unavailable",
            )
        if hold_slot and _IN_FLIGHT >= settings.public_inference_max_concurrency:
            return InferenceDecision(
                False,
                "public_inference_busy",
                "Public replies are busy. Wait and try again.",
            )
        session_times.append(moment)
        _GLOBAL_TIMES.append(moment)
        if hold_slot:
            _IN_FLIGHT += 1
    return None


def finish_public_inference() -> None:
    """Release one live public call. A disabled decision does not hold a slot."""

    global _IN_FLIGHT
    with _LOCK:
        if _IN_FLIGHT:
            _IN_FLIGHT -= 1


def require_public_inference(session_key: str, text: str) -> None:
    decision = assess_public_inference(session_key, text)
    if not decision.allowed:
        status = 429 if decision.code.endswith(("limited", "budget", "busy")) else 503
        if decision.code == "public_inference_rejected":
            status = 422
        if decision.code == "public_inference_input_limited":
            status = 413
        raise AppError(status, decision.code, decision.message)


def _trim(times: list[float], now: float, window: int) -> None:
    cutoff = now - window
    while times and times[0] < cutoff:
        times.pop(0)
