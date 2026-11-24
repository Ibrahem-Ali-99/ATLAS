import pytest

from app.core.errors import AppError
from app.scripts.populate_workspace import _require_sample_org


def test_population_requires_explicit_confirmation() -> None:
    with pytest.raises(AppError, match="Pass --confirm-sample-workspace"):
        _require_sample_org(None, "sample-atlas", False)  # type: ignore[arg-type]


def test_population_rejects_operational_slug() -> None:
    with pytest.raises(AppError, match=r"sample-\* organizations"):
        _require_sample_org(None, "atlas-demo", True)  # type: ignore[arg-type]
