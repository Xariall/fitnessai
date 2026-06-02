from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DB_PATH = Path(__file__).parent / "exercises.json"


@dataclass(frozen=True)
class Exercise:
    name: str
    muscle_group: str
    secondary_muscles: tuple[str, ...]
    equipment: tuple[str, ...]
    joint_load: tuple[str, ...]
    contraindications: tuple[str, ...]
    description: str
    difficulty: str
    is_compound: bool
    uses_bodyweight: bool
    technique_cues: tuple[str, ...]


def _load() -> tuple[Exercise, ...]:
    raw: list[dict] = json.loads(_DB_PATH.read_text(encoding="utf-8"))
    return tuple(
        Exercise(
            name=ex["name"],
            muscle_group=ex["muscle_group"],
            secondary_muscles=tuple(ex.get("secondary_muscles") or []),
            equipment=tuple(ex.get("equipment") or ["none"]),
            joint_load=tuple(ex.get("joint_load") or []),
            contraindications=tuple(ex.get("contraindications") or []),
            description=ex.get("description") or ex["name"],
            difficulty=ex.get("difficulty") or "beginner",
            is_compound=bool(ex.get("is_compound")),
            uses_bodyweight=bool(ex.get("uses_bodyweight")),
            technique_cues=tuple(ex.get("technique_cues") or []),
        )
        for ex in raw
    )


EXERCISE_DB: tuple[Exercise, ...] = _load()

_INJURY_LABELS: dict[str, str] = {
    "knee_injury": "колено",
    "lower_back": "поясница",
    "shoulder_injury": "плечо",
    "elbow": "локоть",
    "wrist": "запястье",
    "hip": "бедро/таз",
    "neck": "шея",
}

VALID_INJURY_TAGS = frozenset(_INJURY_LABELS.keys())


def injury_label(tag: str) -> str:
    return _INJURY_LABELS.get(tag, tag)


def get_safe_exercises(
    focus: str,
    user_injuries: list[str],
    equipment: list[str] | None = None,
    max_count: int = 20,
) -> list[Exercise]:
    """Pure Python filter — no LLM, no IO."""
    focus_lower = focus.lower()
    results = [
        ex for ex in EXERCISE_DB
        if focus_lower in ex.muscle_group
        and not any(inj in ex.contraindications for inj in user_injuries)
        and (
            equipment is None
            or any(eq in ex.equipment for eq in equipment + ["none"])
        )
    ]
    return results[:max_count]
