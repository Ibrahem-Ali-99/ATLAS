import httpx

from app.core.config import get_settings
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain


def post_webhook(url: str, payload: dict[str, object]) -> int:
    settings = get_settings()
    try:
        response = httpx.post(url, json=payload, timeout=settings.n8n_timeout_seconds)
    except httpx.TimeoutException as exc:
        raise OutcomeUncertain("n8n_timeout") from exc
    except httpx.HTTPError as exc:
        raise DeliveryFailed("n8n_unreachable") from exc
    return response.status_code
