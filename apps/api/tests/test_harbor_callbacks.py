from pathlib import Path

from app.domains.assistant.planner import _calendar, plan_request
from app.domains.assistant.tools import tool_schemas


def test_harbor_callback_origin_does_not_replace_the_operational_api() -> None:
    text = Path(__file__).resolve().parents[3].joinpath("infrastructure/compose.yaml").read_text(
        encoding="utf-8"
    )
    assert "ATLAS_PUBLIC_API_URL: ${ATLAS_PUBLIC_API_URL:-http://host.docker.internal:8000}" in text
    assert (
        "http://api:8000,http://host.docker.internal:8000,"
        "http://host.docker.internal:8012,http://host.docker.internal:8013"
        in text
    )


def test_expired_token_recovery_does_not_change_the_webhook() -> None:
    from app.domains.monitoring.service import _connection_recovery

    text, href = _connection_recovery("authentication_required", "WhatsApp access token expired")
    assert text is not None and "webhook callback" in text
    assert href == "/integrations"


def test_an_unchecked_calendar_slot_is_not_described_as_booked() -> None:
    text = _calendar({"available": None, "provider": "google", "needs_time": False})
    assert "not treated as open" in text
    assert "already booked" not in text


def test_provider_health_is_offered_to_the_assistant() -> None:
    names = [item["function"]["name"] for item in tool_schemas()]
    assert "provider_health" in names
    assert "check_availability" in names
    assert "draft_customer_message" in names
    assert "propose_appointment" in names
    decision = plan_request("Which providers are connected?", [])
    assert ("provider_health", {}) in decision.tools
