from preflight import problems


def test_production_configuration_uses_the_same_https_origin() -> None:
    settings = {
        "STAGING_ENVIRONMENT": "production",
        "STAGING_SECRET_KEY": "s" * 40,
        "STAGING_POSTGRES_PASSWORD": "p" * 40,
        "STAGING_N8N_ENCRYPTION_KEY": "n" * 40,
        "STAGING_CREDENTIAL_ENCRYPTION_KEYS": "stage-01=" + "k" * 40,
        "STAGING_HOST": "atlas.localhost",
        "STAGING_HTTPS_PORT": "8443",
        "STAGING_CORS_ORIGINS": "https://atlas.localhost:8443",
        "STAGING_LLM_API_KEY": "c" * 40,
    }
    assert problems(settings) == []
    settings["STAGING_CORS_ORIGINS"] += "/"
    assert problems(settings) == ["STAGING_CORS_ORIGINS must include the staged HTTPS origin"]


def test_preflight_refuses_unsafe_credentials_without_echoing_them() -> None:
    credential = "sk_live_" + "l" * 40
    issues = problems(
        {
            "STAGING_SECRET_KEY": "s" * 40,
            "STAGING_CREDENTIAL_ENCRYPTION_KEYS": "stage-01=" + "s" * 40,
            "STAGING_BILLING_PROVIDER": "stripe",
            "STAGING_STRIPE_SECRET_KEY": credential,
        }
    )
    assert any("independent keyring" in issue for issue in issues)
    assert any("test-mode API key" in issue for issue in issues)
    assert all(credential not in issue for issue in issues)


def test_calendar_callback_validates_origin_and_redacts_secret() -> None:
    settings = {
        "STAGING_GOOGLE_CALENDAR_CLIENT_ID": "fixture.apps.googleusercontent.com",
        "STAGING_GOOGLE_CALENDAR_CLIENT_SECRET": "fixture-" + "k" * 30,
        "STAGING_GOOGLE_CALENDAR_REDIRECT_URI": "https://atlas.localhost/api/v1/calendar/google/callback",
        "STAGING_GOOGLE_CALENDAR_WEB_ORIGIN": "https://atlas.localhost",
    }
    assert not any("Google Calendar" in issue for issue in problems(settings))
    settings["STAGING_GOOGLE_CALENDAR_REDIRECT_URI"] += "?wrong=1"
    issues = problems(settings)
    assert any("Google Calendar OAuth origin" in issue for issue in issues)
    assert all(settings["STAGING_GOOGLE_CALENDAR_CLIENT_SECRET"] not in issue for issue in issues)
