from preflight import EXAMPLE_ENV, problems, read_env


def valid() -> dict[str, str]:
    return {
        "PRODUCTION_ENVIRONMENT": "production",
        "PRODUCTION_PUBLIC_DEMO": "false",
        "PRODUCTION_COOKIE_SECURE": "true",
        "PRODUCTION_LOG_LEVEL": "INFO",
        "PRODUCTION_SECRET_KEY": "s" * 40,
        "PRODUCTION_POSTGRES_USER": "atlas",
        "PRODUCTION_POSTGRES_PASSWORD": "p" * 40,
        "PRODUCTION_POSTGRES_DB": "atlas",
        "PRODUCTION_N8N_ENCRYPTION_KEY": "n" * 40,
        "PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS": "prod-01=" + "k" * 40,
        "PRODUCTION_HOST": "atlas.localhost",
        "PRODUCTION_HTTP_PORT": "19080",
        "PRODUCTION_HTTPS_PORT": "19443",
        "PRODUCTION_CORS_ORIGINS": "https://atlas.localhost:19443",
        "PRODUCTION_CAMPAIGN_PUBLIC_URL": "https://atlas.localhost:19443",
        "PRODUCTION_LLM_PROVIDER": "groq",
        "PRODUCTION_LLM_API_KEY": "c" * 40,
        "PRODUCTION_LLM_MODEL": "llama-3.3-70b-versatile",
        "PRODUCTION_EMBEDDING_PROVIDER": "ollama",
        "PRODUCTION_EMBEDDING_BASE_URL": "http://ollama:11434/v1",
        "PRODUCTION_EMBEDDING_DIMENSIONS": "768",
        "PRODUCTION_EMAIL_MODE": "sandbox",
        "PRODUCTION_SMTP_HOST": "mailpit",
        "PRODUCTION_BILLING_PROVIDER": "sandbox",
        "PRODUCTION_WHATSAPP_LIVE_ENABLED": "false",
    }


def test_valid_local_proof_configuration_passes() -> None:
    assert problems(valid()) == []


def test_example_file_is_rejected_without_echoing_placeholders() -> None:
    issues = problems(read_env(EXAMPLE_ENV))
    rendered = "\n".join(issues)
    assert any("PRODUCTION_SECRET_KEY" in issue for issue in issues)
    assert "replace-with" not in rendered
    assert "replace-with-a-long-random-string" not in rendered


def test_public_hostname_must_use_http_and_https_ports() -> None:
    settings = valid()
    settings["PRODUCTION_HOST"] = "atlas.example"
    settings["PRODUCTION_CORS_ORIGINS"] = "https://atlas.example:19443"
    settings["PRODUCTION_CAMPAIGN_PUBLIC_URL"] = "https://atlas.example:19443"
    assert "A public hostname must publish ports 80 and 443" in problems(settings)
    settings["PRODUCTION_HTTP_PORT"] = "80"
    settings["PRODUCTION_HTTPS_PORT"] = "443"
    settings["PRODUCTION_CORS_ORIGINS"] = "https://atlas.example"
    settings["PRODUCTION_CAMPAIGN_PUBLIC_URL"] = "https://atlas.example"
    assert problems(settings) == []


def test_live_stripe_keys_and_loopback_embeddings_are_rejected() -> None:
    live_key = "sk_live_" + "l" * 24
    settings = valid()
    settings["PRODUCTION_BILLING_PROVIDER"] = "stripe"
    settings["PRODUCTION_STRIPE_SECRET_KEY"] = live_key
    settings["PRODUCTION_EMBEDDING_BASE_URL"] = "http://127.0.0.1:11434/v1"
    settings["PRODUCTION_LLM_PROVIDER"] = "double"
    issues = problems(settings)
    rendered = "\n".join(issues)
    assert "Live Stripe keys are rejected" in issues
    assert "Deterministic providers are not allowed in production" in issues
    assert "PRODUCTION_EMBEDDING_BASE_URL must use the private Ollama service" in issues
    assert live_key not in rendered


def test_database_password_cannot_match_the_user_or_a_default() -> None:
    settings = valid()
    settings["PRODUCTION_POSTGRES_USER"] = "p" * 40
    settings["PRODUCTION_POSTGRES_PASSWORD"] = "p" * 40
    assert any("must not match the database user" in issue for issue in problems(settings))
    settings = valid()
    settings["PRODUCTION_POSTGRES_PASSWORD"] = "atlas"
    rendered = "\n".join(problems(settings))
    assert "PRODUCTION_POSTGRES_PASSWORD" in rendered
    assert "atlas" not in rendered.split("PRODUCTION_POSTGRES_PASSWORD", 1)[-1]
