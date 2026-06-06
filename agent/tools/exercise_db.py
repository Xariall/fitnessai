from __future__ import annotations

import json
import logging
import re as _re
import unicodedata as _ud
from dataclasses import dataclass
from pathlib import Path

_DB_PATH = Path(__file__).parent / "exercises.json"
_RU_PATH = Path(__file__).parent / "exercises_ru.json"

logger = logging.getLogger(__name__)


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


def _normalize_key(name: str) -> str:
    """Canonical key: 'Bench-Press', 'жим лёжа', 'BENCH PRESS' → unified lowercase form."""
    s = _ud.normalize("NFC", name.lower().strip())
    s = s.replace("ё", "е").replace("-", " ")
    s = _re.sub(r"\s+", " ", s)
    return s


def _load_ru() -> tuple[dict[str, str], dict[str, str]]:
    """Load Russian exercise name mappings. Returns (en_key→ru_name, ru_key→en_name)."""
    if not _RU_PATH.exists():
        return {}, {}
    raw: dict[str, str] = json.loads(_RU_PATH.read_text(encoding="utf-8"))
    forward: dict[str, str] = {_normalize_key(k): v for k, v in raw.items()}
    reverse: dict[str, str] = {}
    for en_name, ru_name in raw.items():
        ru_key = _normalize_key(ru_name)
        if ru_key in reverse:
            logger.warning(
                "RU name collision: '%s' maps to both '%s' and '%s'",
                ru_name, reverse[ru_key], en_name,
            )
        else:
            reverse[ru_key] = en_name
    return forward, reverse


try:
    _RU, _RU_REVERSE = _load_ru()
except Exception as _load_err:
    logger.warning("Не удалось загрузить русские названия упражнений: %s", _load_err)
    _RU: dict[str, str] = {}
    _RU_REVERSE: dict[str, str] = {}


def get_ru_name(en_name: str) -> str:
    """Вернуть русское название упражнения (fallback — английское)."""
    return _RU.get(_normalize_key(en_name), en_name)


def resolve_ru_to_en(name: str) -> str:
    """Преобразовать русское название в английский ключ DB. Если не найдено — вернуть как есть."""
    return _RU_REVERSE.get(_normalize_key(name), name)


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
