from preflight import EXAMPLE_ENV, problems, read_env


def valid() -> dict[str, str]:
    return {
        "PORTFOLIO_ENVIRONMENT": "development",
        "PORTFOLIO_PUBLIC_DEMO": "true",
        "PORTFOLIO_COOKIE_SECURE": "true",
        "PORTFOLIO_LOG_LEVEL": "INFO",
        "PORTFOLIO_SECRET_KEY": "s" * 40,
        "PORTFOLIO_POSTGRES_USER": "atlas",
        "PORTFOLIO_POSTGRES_PASSWORD": "p" * 40,
        "PORTFOLIO_POSTGRES_DB": "atlas_portfolio",
        "PORTFOLIO_CREDENTIAL_ENCRYPTION_KEYS": "demo-01=" + "k" * 40,
        "PORTFOLIO_HOST": "atlas.localhost",
        "PORTFOLIO_HTTP_PORT": "19380",
        "PORTFOLIO_HTTPS_PORT": "19343",
        "PORTFOLIO_CORS_ORIGINS": "https://atlas.localhost:19343",
        "PORTFOLIO_CAMPAIGN_PUBLIC_URL": "https://atlas.localhost:19343",
        "PORTFOLIO_LLM_API_KEY": "",
        "PORTFOLIO_EMBEDDING_API_KEY": "",
        "PORTFOLIO_STRIPE_SECRET_KEY": "",
        "PORTFOLIO_GOOGLE_CALENDAR_CLIENT_SECRET": "",
    }


def test_valid_local_configuration_passes() -> None:
    assert problems(valid()) == []


def test_example_file_is_rejected_without_echoing_placeholders() -> None:
    issues = problems(read_env(EXAMPLE_ENV))
    rendered = "\n".join(issues)
    assert any("PORTFOLIO_SECRET_KEY" in issue for issue in issues)
    assert "replace-with" not in rendered


def test_public_hostname_must_use_http_and_https_ports() -> None:
    settings = valid()
    settings["PORTFOLIO_HOST"] = "demo.example"
    settings["PORTFOLIO_CORS_ORIGINS"] = "https://demo.example:19343"
    settings["PORTFOLIO_CAMPAIGN_PUBLIC_URL"] = "https://demo.example:19343"
    assert "A public hostname must publish ports 80 and 443" in problems(settings)
    settings["PORTFOLIO_HTTP_PORT"] = "80"
    settings["PORTFOLIO_HTTPS_PORT"] = "443"
    settings["PORTFOLIO_CORS_ORIGINS"] = "https://demo.example"
    settings["PORTFOLIO_CAMPAIGN_PUBLIC_URL"] = "https://demo.example"
    assert problems(settings) == []


def test_provider_keys_live_stripe_and_other_databases_are_rejected() -> None:
    settings = valid()
    settings["PORTFOLIO_ENVIRONMENT"] = "production"
    settings["PORTFOLIO_PUBLIC_DEMO"] = "false"
    settings["PORTFOLIO_POSTGRES_DB"] = "atlas"
    settings["PORTFOLIO_LLM_API_KEY"] = "gsk_" + "k" * 20
    settings["PORTFOLIO_STRIPE_SECRET_KEY"] = "sk_live_" + "l" * 20
    issues = problems(settings)
    rendered = "\n".join(issues)
    assert any("must be development" in issue for issue in issues)
    assert "PORTFOLIO_PUBLIC_DEMO must be true" in issues
    assert "PORTFOLIO_POSTGRES_DB must be atlas_portfolio" in issues
    assert "PORTFOLIO_LLM_API_KEY must stay empty on the public demo" in issues
    assert "Live Stripe keys are rejected" in issues
    assert "gsk_" not in rendered
    assert "sk_live_" not in rendered


def test_public_groq_key_stays_off_until_authorized() -> None:
    settings = valid()
    settings["PORTFOLIO_PUBLIC_LLM_API_KEY"] = "gsk_public_" + "k" * 24
    issues = problems(settings)
    rendered = "\n".join(issues)
    assert any("must stay empty until public chat is authorized" in issue for issue in issues)
    assert "gsk_public_" not in rendered
    settings["PORTFOLIO_PUBLIC_LLM_AUTHORIZED"] = "true"
    settings["PORTFOLIO_PUBLIC_INFERENCE_ENABLED"] = "true"
    assert problems(settings) == []


def test_database_password_cannot_match_the_user() -> None:
    settings = valid()
    settings["PORTFOLIO_POSTGRES_USER"] = "p" * 40
    settings["PORTFOLIO_POSTGRES_PASSWORD"] = "p" * 40
    assert any("must not match the database user" in issue for issue in problems(settings))
