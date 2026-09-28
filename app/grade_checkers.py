"""Grade checker options map master template DK- names to a work-order prefix."""

from __future__ import annotations

from dataclasses import dataclass

from app.settings import MASTER_TEMPLATE_SEARCH


@dataclass(frozen=True)
class GradeChecker:
    id: str
    label: str
    search: str
    replace: str

    @property
    def prefix(self) -> str:
        return self.replace


GRADE_CHECKERS: tuple[GradeChecker, ...] = (
    GradeChecker(
        id="ryan-kolt",
        label="Ryan Kolt",
        search=MASTER_TEMPLATE_SEARCH,
        replace="RK-",
    ),
)

_BY_ID = {checker.id: checker for checker in GRADE_CHECKERS}


def get_grade_checker(checker_id: str) -> GradeChecker:
    cleaned = (checker_id or "").strip()
    match = _BY_ID.get(cleaned)
    if match is None:
        labels = ", ".join(checker.label for checker in GRADE_CHECKERS)
        raise ValueError(f"Choose a grade checker. Available: {labels}")
    return match


def grade_checkers_for_api() -> list[dict[str, str]]:
    return [
        {
            "id": checker.id,
            "label": checker.label,
            "prefix": checker.prefix,
            "description": f"{checker.label} → {checker.prefix}",
        }
        for checker in GRADE_CHECKERS
    ]
