from project import LIVE_PROJECT, ProjectRefused, assert_project


def test_live_portfolio_project_is_allowed() -> None:
    assert assert_project(LIVE_PROJECT) == LIVE_PROJECT


def test_proof_project_is_allowed() -> None:
    assert assert_project("atlas-portfolio-proof") == "atlas-portfolio-proof"


def test_other_workspaces_are_refused() -> None:
    for name in ("atlas", "atlas-staging", "atlas-production", "atlas-portfolio-other", ""):
        try:
            assert_project(name)
        except ProjectRefused:
            continue
        raise AssertionError(name)
