from compose_contract import CADDY_FILE, COMPOSE_FILE, problems


def test_portfolio_compose_stays_sandboxed_and_small() -> None:
    issues = problems(COMPOSE_FILE.read_text(encoding="utf-8"), CADDY_FILE.read_text(encoding="utf-8"))
    assert issues == []


def test_public_origin_keeps_secure_cookies_and_hides_the_schema() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    caddy = CADDY_FILE.read_text(encoding="utf-8")
    assert 'ATLAS_ENVIRONMENT: development' in compose
    assert 'ATLAS_PUBLIC_DEMO: "true"' in compose
    assert 'ATLAS_COOKIE_SECURE: "true"' in compose
    assert 'startsWith("/docs")' in caddy
    assert '== "/openapi.json"' in caddy
    assert 'startsWith("/redoc")' in caddy
    assert 'respond "Not found" 404' in caddy
    assert "Strict-Transport-Security" in caddy


def test_memory_limits_fit_the_portfolio_host() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    limits = [int(value) for value in __import__("re").findall(r"memory: (\d+)M", text)]
    assert limits == [64, 384, 768, 512, 64]
    assert sum(limits) < 2048
