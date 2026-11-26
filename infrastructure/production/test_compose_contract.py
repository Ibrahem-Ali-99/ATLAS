from pathlib import Path

from compose_contract import COMPOSE_FILE, problems


def test_production_compose_matches_the_contract() -> None:
    assert problems(COMPOSE_FILE.read_text(encoding="utf-8")) == []


def test_postgres_cannot_publish_a_host_port() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    text = text.replace(
        "    image: pgvector/pgvector:pg17\n",
        '    image: pgvector/pgvector:pg17\n    ports:\n      - "5432:5432"\n',
        1,
    )
    assert any("postgres publishes a host port" in issue for issue in problems(text))


def test_scheduler_files_do_not_publish_ports_or_secrets() -> None:
    directory = Path(__file__).resolve().parent
    service = (directory / "atlas-production-backup.service").read_text(encoding="utf-8")
    timer = (directory / "atlas-production-backup.timer").read_text(encoding="utf-8")
    example = (directory / "backup.env.example").read_text(encoding="utf-8")
    assert "infrastructure/production/backup.py" in service
    assert "ports:" not in service
    assert timer.count("OnCalendar=") == 1
    assert "Persistent=true" in timer
    assert "atlas-production-backup.service" in timer
    assert "replace-with-a-long-random-string" in example
    assert "AKIA" not in example
