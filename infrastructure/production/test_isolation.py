import pytest
from isolation import assert_owned


def test_drill_names_are_allowed() -> None:
    assert_owned("atlas-prod-drill-pg")
    assert_owned("atlas-prod-image-proof-api")


def test_live_projects_are_refused() -> None:
    for name in ("atlas-postgres-1", "atlas-staging-postgres-1", "atlas-n8n-1", "postgres"):
        with pytest.raises(RuntimeError, match="refusing to touch"):
            assert_owned(name)
