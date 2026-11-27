from compose_contract import CADDY_FILE, COMPOSE_FILE, problems


def test_portfolio_compose_stays_sandboxed_and_small() -> None:
    issues = problems(COMPOSE_FILE.read_text(encoding="utf-8"), CADDY_FILE.read_text(encoding="utf-8"))
    assert issues == []


def test_memory_limits_fit_the_portfolio_host() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    limits = [int(value) for value in __import__("re").findall(r"memory: (\d+)M", text)]
    assert limits == [64, 384, 768, 512, 64, 1792, 256]
    assert sum(limits) < 4096
