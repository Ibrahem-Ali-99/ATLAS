import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.automation import signatures
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_integration_credentials_use_authenticated_versioned_encryption(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CREDENTIAL_ENCRYPTION_KEYS", "current=alpha-secret,old=old-secret")
    get_settings.cache_clear()
    stored = seal_integration_secret("provider-token")

    assert stored.startswith("enc:v2:current:")
    assert "provider-token" not in stored
    assert open_integration_secret(stored) == "provider-token"


def test_rotated_keyring_can_read_old_key_but_new_seals_use_current(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CREDENTIAL_ENCRYPTION_KEYS", "old=old-secret")
    get_settings.cache_clear()
    stored = seal_integration_secret("rotating-token")

    monkeypatch.setenv("ATLAS_CREDENTIAL_ENCRYPTION_KEYS", "current=new-secret,old=old-secret")
    get_settings.cache_clear()
    assert open_integration_secret(stored) == "rotating-token"
    replacement = seal_integration_secret("replacement-token")
    assert replacement.startswith("enc:v2:current:")
    assert open_integration_secret(replacement) == "replacement-token"


def test_legacy_v1_records_remain_readable(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_SECRET_KEY", "legacy-test-secret-key-with-32-chars")
    get_settings.cache_clear()
    legacy = "enc:v1:" + signatures._fernet().encrypt(b"legacy-token").decode()

    assert open_integration_secret(legacy) == "legacy-token"


def test_unknown_or_tampered_credential_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CREDENTIAL_ENCRYPTION_KEYS", "current=alpha-secret")
    get_settings.cache_clear()
    stored = seal_integration_secret("provider-token")
    tampered = stored[:-1] + ("a" if stored[-1] != "a" else "b")

    with pytest.raises(AppError):
        open_integration_secret(tampered)
