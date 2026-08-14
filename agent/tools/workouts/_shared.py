"""Общие приватные хелперы и константы, используемые в ≥2 модулях пакета workouts.

Ничего отсюда не декорировано @tool — это внутренние утилиты, а не
зарегистрированные инструменты агента.
"""
import re as _re
import unicodedata as _ud
from datetime import datetime, timedelta, timezone

from db.client import fetch, fetchrow

def _normalize_key(name: str) -> str:
    """Canonical exercise key: 'Bench-Press', 'жим лёжа', 'BENCH PRESS' → unified key."""
    s = _ud.normalize("NFC", name.lower().strip())
    s = s.replace("ё", "е").replace("-", " ")
    s = _re.sub(r"\s+", " ", s)
    return s


def _parse_reps(reps) -> tuple[int, int]:
    """Parse "8-10", "8 - 10", "8–10", "8", 10 → (lo, hi). Returns (0, 0) on failure."""
    s = str(reps).strip()
    m = _re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _re.search(r"(\d+)", s)
    if m:
        v = int(m.group(1))
        return v, v
    return 0, 0


def _enrich_exercises_with_ru(exercises: list[dict]) -> list[dict]:
    """Добавить поле name_ru к каждому упражнению. Возвращает новый список (без мутации)."""
    from agent.tools.exercise_db import get_ru_name
    return [{**ex, "name_ru": get_ru_name(ex.get("name") or "")} for ex in exercises]


_MUSCLE_KEYWORDS: dict[str, list[str]] = {
    "chest": ["грудь", "жим", "chest", "отжимания", "грудных"],
    "back": ["спина", "тяга", "подтягивания", "back", "спины"],
    "legs": ["ноги", "приседания", "выпады", "ягодицы", "legs", "квадрицепс", "бедра"],
    "shoulders": ["плечи", "дельты", "жим сидя", "shoulders", "плечей"],
    "arms": ["руки", "бицепс", "трицепс", "arms"],
    "biceps": ["бицепс", "biceps", "curl"],
    "triceps": ["трицепс", "triceps"],
    "core": ["пресс", "кор", "core", "планка", "скручивания"],
    "cardio": ["кардио", "бег", "cardio", "велосипед", "скакалка"],
    "strength": ["сила", "strength", "силовая"],
    "flexibility": ["растяжка", "гибкость", "flexibility", "мобилити"],
}


def _calc_1rm(weight: float, reps: int) -> float:
    """Формула Эпли: оценка 1RM по рабочему весу и повторениям."""
    if reps <= 0 or weight <= 0:
        return 0.0
    if reps == 1:
        return weight
    return round(weight * (1 + reps / 30), 1)


_INCREMENT_COMPOUND = 2.5
_INCREMENT_ISOLATION = 1.25
_NO_WEIGHT_EQUIPMENT = frozenset({"none"})


async def _get_recent_plan(user_id: str, focus: str, days: int = 7) -> dict | None:
    """Look up last workout with matching focus within the given day window."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await fetch(
        "SELECT id, title, plan, created_at FROM workouts "
        "WHERE user_id = $1 AND created_at >= $2 "
        "ORDER BY created_at DESC LIMIT 10",
        user_id, since,
    )
    focus_lower = focus.lower()
    keywords = _MUSCLE_KEYWORDS.get(focus_lower, [focus_lower])
    for row in rows:
        title_lower = (row.get("title") or "").lower()
        if any(kw in title_lower for kw in keywords):
            plan = row.get("plan") or {}
            exercises = plan.get("exercises", [])
            exercises_summary = ", ".join(
                f"{ex.get('name', '')} {ex.get('sets', '')}×{ex.get('reps', '')}"
                for ex in exercises[:6]
            )
            log_rows = await fetch(
                "SELECT performance, done_as_planned FROM workout_logs "
                "WHERE user_id = $1 AND workout_id = $2 "
                "ORDER BY completed_at DESC LIMIT 1",
                user_id, row["id"],
            )
            last_log = (log_rows or [None])[0]
            return {
                "title": row["title"],
                "exercises_summary": exercises_summary,
                "plan_exercises": exercises,
                "last_performance": (last_log or {}).get("performance") or [],
                "last_done_as_planned": (last_log or {}).get("done_as_planned", False),
            }
    return None


async def _get_active_cycle_data(user_id: str) -> dict | None:
    """Return the active training_cycles row for a user, or None."""
    return await fetchrow(
        "SELECT * FROM training_cycles WHERE user_id = $1 AND status = 'active' "
        "ORDER BY created_at DESC LIMIT 1",
        user_id,
    )


async def _advance_cycle_position(user_id: str, cycle_id: str) -> dict:
    """Advance current_session_index; roll to next week when sessions exhausted.

    Uses optimistic locking to guard against concurrent writes — if the row
    changed between read and update, returns reason="concurrent_update".
    """
    row = await fetchrow(
        "SELECT * FROM training_cycles WHERE id = $1 AND user_id = $2",
        cycle_id, user_id,
    )

    if not row:
        return {"advanced": False, "reason": "cycle_not_found"}
    if row["status"] != "active":
        return {"advanced": False, "reason": "not_active", "status": row["status"]}

    cur_sess  = row["current_session_index"]
    cur_week  = row["current_week"]
    sess_per  = row["sessions_per_week"]
    total_wks = row["total_weeks"]
    done      = row["total_sessions_done"] + 1

    next_sess = cur_sess + 1
    next_week = cur_week
    if next_sess >= sess_per:
        next_sess = 0
        next_week += 1

    is_complete = next_week > total_wks
    new_status  = "completed" if is_complete else "active"

    set_clauses = [
        "current_session_index = $1",
        "current_week = $2",
        "total_sessions_done = $3",
        "status = $4",
    ]
    args: list = [next_sess, min(next_week, total_wks), done, new_status]

    if is_complete and not row.get("completed_at"):
        set_clauses.append(f"completed_at = ${len(args) + 1}")
        args.append(datetime.now(timezone.utc))

    # Optimistic locking: only update if position AND status haven't changed
    guard_start = len(args) + 1
    query = (
        f"UPDATE training_cycles SET {', '.join(set_clauses)} "
        f"WHERE id = ${guard_start} AND current_session_index = ${guard_start + 1} "
        f"AND current_week = ${guard_start + 2} AND status = 'active' "
        f"RETURNING *"
    )
    args.extend([cycle_id, cur_sess, cur_week])

    result = await fetchrow(query, *args)

    if result is None:
        return {"advanced": False, "reason": "concurrent_update"}

    return {
        "advanced": True,
        "new_week": next_week,
        "new_session_index": next_sess,
        "is_complete": is_complete,
        "total_sessions_done": done,
    }
