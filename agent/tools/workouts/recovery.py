"""Восстановление мышечных групп и травмы/противопоказания."""
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from db.client import execute, fetch, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _MUSCLE_KEYWORDS

logger = logging.getLogger(__name__)


@tool
async def get_recovery_overview(telegram_user_id: int) -> dict:
    """Получить статус восстановления по всем основным группам мышц за один вызов.

    Используй этот инструмент когда нужен общий обзор восстановления — вместо
    того чтобы вызывать check_recovery_status отдельно для каждой группы.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    from agent.tools.exercise_db import get_safe_exercises

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"groups": {}, "recommended": [], "injuries": [], "error": "Пользователь не найден."}

    profile_row = await fetchrow(
        "SELECT injuries FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    injuries: list[str] = (profile_row or {}).get("injuries") or []

    since_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    logs = await fetch(
        "SELECT wl.completed_at, wl.notes, w.title AS workout_title, w.plan AS workout_plan "
        "FROM workout_logs wl LEFT JOIN workouts w ON wl.workout_id = w.id "
        "WHERE wl.user_id = $1 AND wl.completed_at >= $2 "
        "ORDER BY wl.completed_at DESC",
        user_id, since_48h,
    )

    # Pre-compute combined text once per log entry (reused across all 7 group checks)
    log_entries: list[tuple[str, str]] = []
    for log in logs:
        notes_lower = (log.get("notes") or "").lower()
        title_lower = (log.get("workout_title") or "").lower()
        plan = log.get("workout_plan") or {}
        exercises_text = " ".join(
            ex.get("name", "").lower() for ex in plan.get("exercises", [])
        )
        log_entries.append((f"{notes_lower} {title_lower} {exercises_text}", log["completed_at"]))

    _MAIN_GROUPS = ["chest", "back", "legs", "shoulders", "arms", "core", "cardio"]
    groups: dict = {}
    recommended: list[str] = []

    for group in _MAIN_GROUPS:
        contraindicated = not get_safe_exercises(group, injuries, max_count=1) and bool(injuries)

        status = "contraindicated" if contraindicated else "ready"
        hours_since_last: int | None = None
        keywords = _MUSCLE_KEYWORDS.get(group, [group])

        if not contraindicated:
            for combined, completed_at in log_entries:
                if any(kw in combined for kw in keywords):
                    ts = completed_at.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts)
                    hours_since_last = round(
                        (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
                    )
                    status = "needs_rest"
                    break

        groups[group] = {
            "status": status,
            "hours_since_last": hours_since_last,
            "contraindicated": contraindicated,
        }
        if status == "ready":
            recommended.append(group)

    return {"groups": groups, "recommended": recommended, "injuries": injuries}


@tool
async def check_recovery_status(
    telegram_user_id: int,
    muscle_group: str,
) -> dict:
    """Check if a muscle group has recovered and is ready to train (48h rule).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        muscle_group: Группа мышц (chest/back/legs/shoulders/arms/core/cardio).
    """
    from agent.tools.exercise_db import get_safe_exercises, injury_label

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"can_train": True, "status": "ready", "message": "Нет данных о тренировках — начинай!"}

    # Check for contraindications first
    profile_row = await fetchrow(
        "SELECT injuries FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    injuries: list[str] = (profile_row or {}).get("injuries") or []
    safe = get_safe_exercises(muscle_group, injuries, max_count=1)
    if not safe and injuries:
        listed = ", ".join(injury_label(i) for i in injuries)
        return {
            "can_train": False,
            "status": "contraindicated",
            "message": (
                f"Из-за травм ({listed}) для группы «{muscle_group}» нет безопасных упражнений. "
                f"Рекомендую другую группу мышц или растяжку."
            ),
        }

    # 48h recovery check
    since_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    logs = await fetch(
        "SELECT wl.completed_at, wl.notes, w.title AS workout_title, w.plan AS workout_plan "
        "FROM workout_logs wl LEFT JOIN workouts w ON wl.workout_id = w.id "
        "WHERE wl.user_id = $1 AND wl.completed_at >= $2 "
        "ORDER BY wl.completed_at DESC",
        user_id, since_48h,
    )

    if not logs:
        return {
            "can_train": True,
            "status": "ready",
            "message": "Последние 48 часов без тренировок. Готов к работе 💪",
            "last_trained": None,
        }

    keywords = _MUSCLE_KEYWORDS.get(muscle_group.lower(), [muscle_group.lower()])
    for log in logs:
        notes_lower = (log.get("notes") or "").lower()
        title_lower = (log.get("workout_title") or "").lower()
        plan = log.get("workout_plan") or {}
        exercises_text = " ".join(
            ex.get("name", "").lower() for ex in plan.get("exercises", [])
        )
        combined = f"{notes_lower} {title_lower} {exercises_text}"

        if any(kw in combined for kw in keywords):
            completed_at = log["completed_at"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(completed_at)
            hours_ago = round(
                (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
            )
            return {
                "can_train": False,
                "status": "needs_rest",
                "message": (
                    f"Группа «{muscle_group}» тренировалась {hours_ago}ч назад. "
                    "Рекомендуется отдых или другая группа мышц."
                ),
                "hours_since_last": hours_ago,
                "last_trained": log["completed_at"],
            }

    return {
        "can_train": True,
        "status": "ready",
        "message": f"Группа «{muscle_group}» готова — за последние 48 часов не тренировалась.",
        "last_trained": None,
    }


@tool
async def update_user_injuries(telegram_user_id: int, injuries: list[str]) -> str:
    """Обновить список травм/противопоказаний пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        injuries: Список тегов травм (knee_injury/lower_back/shoulder_injury/elbow/wrist/hip/neck).
                  Передай [] чтобы очистить список.
    """
    from agent.tools.exercise_db import VALID_INJURY_TAGS, injury_label

    unknown = [i for i in injuries if i not in VALID_INJURY_TAGS]
    if unknown:
        valid = ", ".join(sorted(VALID_INJURY_TAGS))
        logger.warning("Unknown injury tags: %s. Valid: %s", unknown, valid)

    await execute(
        "UPDATE users SET injuries = $1 WHERE telegram_user_id = $2",
        injuries, telegram_user_id,
    )

    if not injuries:
        return "Список травм очищен. Буду предлагать все упражнения без ограничений."

    listed = ", ".join(injury_label(i) for i in injuries)
    return (
        f"Записал противопоказания: {listed}. "
        f"Буду автоматически исключать опасные упражнения при составлении тренировок."
    )
