"""Opt-in live provider smoke. CI does not set the flag, so this stays skipped."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_LIVE_PROVIDERS") != "yes",
    reason="Set ATLAS_LIVE_PROVIDERS=yes to call Groq and Ollama",
)


def test_live_providers_are_opt_in() -> None:
    from app.scripts import live_providers

    live_providers.main()
