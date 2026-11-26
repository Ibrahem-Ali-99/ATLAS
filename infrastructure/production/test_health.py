from health import summarize


def test_healthy_stack_passes() -> None:
    rows = [
        {"Service": name, "State": "running", "Health": "healthy"}
        for name in ("caddy", "web", "api", "postgres", "mailpit", "n8n", "ollama")
    ]
    rows.append({"Service": "embedding-model", "State": "exited", "ExitCode": 0})
    assert summarize(rows) == []


def test_unhealthy_api_is_reported() -> None:
    rows = [
        {"Service": name, "State": "running", "Health": "healthy"}
        for name in ("caddy", "web", "postgres", "mailpit", "n8n", "ollama")
    ]
    rows.append({"Service": "api", "State": "running", "Health": "unhealthy"})
    issues = summarize(rows)
    assert any(issue.startswith("api is") for issue in issues)
