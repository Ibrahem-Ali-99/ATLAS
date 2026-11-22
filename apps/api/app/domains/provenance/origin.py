"""Record origin for business data.

Origin lives on the record, not on the organization. One tenant can hold
operational work, a demonstration row, and an evaluation run at the same time.
A name is not evidence of origin.
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.errors import AppError


class Origin(StrEnum):
    operational = "operational"
    demo = "demo"
    evaluation = "evaluation"
    unknown = "unknown"


class DataScope(StrEnum):
    operational = "operational"
    demo = "demo"
    evaluation = "evaluation"
    unknown = "unknown"
    all = "all"


ORIGIN = Enum(
    Origin,
    name="record_origin",
    values_callable=lambda members: [member.value for member in members],
    native_enum=True,
    create_type=False,
)

_LABELS = {
    Origin.operational: "operational",
    Origin.demo: "demo",
    Origin.evaluation: "evaluation",
    Origin.unknown: "legacy",
}


def origin_column() -> Mapped[Origin]:
    return mapped_column(
        ORIGIN,
        nullable=False,
        default=Origin.unknown,
        server_default=Origin.unknown.value,
    )


def stated_origin(value: object, *, default: Origin = Origin.operational) -> Origin:
    if value is None:
        return default
    if isinstance(value, Origin):
        return value
    if isinstance(value, str):
        try:
            return Origin(value)
        except ValueError as exc:
            raise AppError(
                422,
                "invalid_origin",
                "Origin must be operational, demo, evaluation, or unknown",
            ) from exc
    raise AppError(
        422,
        "invalid_origin",
        "Origin must be operational, demo, evaluation, or unknown",
    )


def scope_clause(column: Any, scope: DataScope) -> Any | None:
    if scope is DataScope.all:
        return None
    return column == Origin(scope.value)


def provenance_notice(scope: DataScope, counts: dict[str, int]) -> str:
    mix = ", ".join(f"{counts[item.value]} {_LABELS[item]}" for item in Origin)
    if scope is DataScope.all:
        return f"All stored leads. {mix}."
    label = _LABELS[Origin(scope.value)]
    outside = sum(count for key, count in counts.items() if key != scope.value)
    return (
        f"This view counts {label} records. Stored leads by origin: {mix}. "
        f"{outside} leads are outside this view."
    )
