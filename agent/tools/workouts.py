import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)


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


async def _get_recent_plan(user_id: str, focus: str, days: int = 7) -> dict | None:
    """Look up last workout with matching focus within the given day window."""
    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        await client.table("workouts")
        .select("title, plan, created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    rows = result.data or []
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
            return {"title": row["title"], "exercises_summary": exercises_summary}
    return None


@tool
async def generate_workout_plan(
    telegram_user_id: int,
    focus: str,
    duration_minutes: int,
    equipment: Optional[str] = None,
) -> dict:
    """Сгенерировать план тренировки на основе профиля пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        focus: Группа мышц или тип (chest/back/legs/shoulders/arms/core/cardio/strength/flexibility).
        duration_minutes: Длительность тренировки в минутах.
        equipment: Доступное оборудование. Передай 'none' для тренировки только с весом тела (дома, без инвентаря).
                   Варианты: none / barbell / dumbbells / cable / machine / bands / kettlebells.
                   Если не указано — будут предложены упражнения с любым инвентарём.
    """
    import json
    import re

    from agent.tools.exercise_db import get_safe_exercises
    from llm.provider import get_llm

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    injuries: list[str] = profile.get("injuries") or []

    user_id = await _get_user_id(telegram_user_id)

    # Check for a recent workout with the same focus for progressive overload
    progressive_note = ""
    if user_id:
        recent = await _get_recent_plan(user_id, focus, days=7)
        if recent:
            progressive_note = (
                f"ВАЖНО — ПРОГРЕССИЯ: недавно пользователь делал тренировку '{recent['title']}'. "
                f"Упражнения были: {recent['exercises_summary']}. "
                f"Используй те же упражнения и добавь прогрессию: +5–10% веса или +1–2 повторения."
            )

    # Filter safe exercises in Python — no LLM needed for this step
    eq_filter = [equipment] if equipment else None
    safe = get_safe_exercises(focus, injuries, equipment=eq_filter, max_count=15)
    if not safe:
        return {
            "title": f"Тренировка: {focus}",
            "exercises": [],
            "error": (
                f"Нет доступных упражнений для группы '{focus}' "
                f"с учётом противопоказаний. Попробуй другую группу мышц."
            ),
        }

    exercises_context = "\n".join(
        f"- {ex.name}: {ex.description}" for ex in safe
    )

    llm = get_llm()
    prompt = (
        f"Составь план тренировки.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, рост {profile.get('height_cm')} см, "
        f"цель: {profile.get('goal')}, активность: {profile.get('activity_level')}.\n"
        f"Фокус: {focus}. Длительность: {duration_minutes} минут.\n"
        f"{progressive_note}\n\n"
        f"Используй ТОЛЬКО упражнения из этого списка (выбери 4–6 подходящих):\n"
        f"{exercises_context}\n\n"
        f"Верни JSON:\n"
        f'{{"title": "...", "exercises": [{{"name": "...", "sets": 3, "reps": "10-12", "rest_seconds": 60}}]}}'
    )

    try:
        response = await llm.ainvoke(prompt)
        raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
    except Exception:
        logger.exception("LLM call failed in generate_workout_plan for user %s", telegram_user_id)
        return {"title": f"Тренировка: {focus}", "exercises": [], "error": "Ошибка генерации плана"}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        plan = json.loads(match.group()) if match else {"title": f"Тренировка: {focus}", "exercises": []}
    except json.JSONDecodeError:
        logger.warning("JSON parse failed in generate_workout_plan, raw=%r", raw[:200])
        plan = {"title": f"Тренировка: {focus}", "exercises": []}

    if user_id:
        try:
            saved = (
                await client.table("workouts")
                .insert({"user_id": user_id, "title": plan.get("title", focus), "plan": plan})
                .execute()
            )
            plan["id"] = saved.data[0]["id"] if saved.data else None
        except Exception:
            logger.exception("Failed to save workout to DB for user %s", telegram_user_id)

    return plan


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

    client = await get_client()
    await (
        client.table("users")
        .update({"injuries": injuries})
        .eq("telegram_user_id", telegram_user_id)
        .execute()
    )

    if not injuries:
        return "Список травм очищен. Буду предлагать все упражнения без ограничений."

    listed = ", ".join(injury_label(i) for i in injuries)
    return (
        f"Записал противопоказания: {listed}. "
        f"Буду автоматически исключать опасные упражнения при составлении тренировок."
    )


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

    client = await get_client()

    profile_result = (
        await client.table("users")
        .select("injuries")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    injuries: list[str] = (profile_result.data or {}).get("injuries") or []

    since_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    result = (
        await client.table("workout_logs")
        .select("completed_at, notes, workouts(title, plan)")
        .eq("user_id", user_id)
        .gte("completed_at", since_48h)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = result.data or []

    # Pre-compute combined text once per log entry (reused across all 7 group checks)
    log_entries: list[tuple[str, str]] = []
    for log in logs:
        notes_lower = (log.get("notes") or "").lower()
        workout = log.get("workouts") or {}
        title_lower = (workout.get("title") or "").lower()
        plan = workout.get("plan") or {}
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
async def log_workout(
    telegram_user_id: int,
    notes: str,
    workout_id: Optional[str] = None,
) -> str:
    """Записать выполненную тренировку."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return "Пользователь не найден."

    client = await get_client()
    record: dict = {
        "user_id": user_id,
        "notes": notes,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if workout_id:
        record["workout_id"] = workout_id

    await client.table("workout_logs").insert(record).execute()
    return "Тренировка записана! Отличная работа 💪"


@tool
async def get_workout_history(telegram_user_id: int, limit: int = 5) -> list[dict]:
    """Получить историю тренировок пользователя (последние N записей)."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return []

    client = await get_client()
    result = (
        await client.table("workout_logs")
        .select("*, workouts(title)")
        .eq("user_id", user_id)
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


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

    client = await get_client()

    # Check for contraindications first
    profile_result = (
        await client.table("users")
        .select("injuries")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    injuries: list[str] = (profile_result.data or {}).get("injuries") or []
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
    since_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    result = (
        await client.table("workout_logs")
        .select("completed_at, notes, workouts(title, plan)")
        .eq("user_id", user_id)
        .gte("completed_at", since_48h)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = result.data or []

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
        workout = log.get("workouts") or {}
        title_lower = (workout.get("title") or "").lower()
        plan = workout.get("plan") or {}
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
async def create_training_cycle(
    telegram_user_id: int,
    goal: str,
    weeks: int = 4,
) -> dict:
    """Create a multi-week periodized training mesocycle (4–8 weeks).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        goal: Цель (gain_muscle / lose_weight / strength / endurance).
        weeks: Количество недель (4–8).
    """
    import json
    import re

    from llm.provider import get_llm

    weeks = max(4, min(weeks, 8))

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    injuries: list[str] = profile.get("injuries") or []

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"ПРОТИВОПОКАЗАНИЯ: {listed}. Исключи упражнения с нагрузкой на эти зоны.\n"

    llm = get_llm()
    prompt = (
        f"Составь мезоцикл тренировок на {weeks} недель.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
        f"{injuries_note}"
        f"Принципы:\n"
        f"- Недели 1–{weeks//2}: накопление объёма (умеренная нагрузка)\n"
        f"- Недели {weeks//2+1}–{weeks-1}: интенсификация (+5% веса, -10% объёма)\n"
        f"- Последняя неделя: deload (снижение нагрузки на 30%)\n"
        f"- Двойная прогрессия: сначала повторения до верхней границы диапазона, потом вес\n\n"
        f"Верни JSON:\n"
        f'{{"title": "...", "goal": "...", "weeks": {weeks}, '
        f'"cycle": [{{"week": 1, "theme": "Накопление объёма", '
        f'"sessions": [{{"day": "Понедельник", "focus": "...", '
        f'"exercises": [{{"name": "...", "sets": 3, "reps": "10-12", "rest_seconds": 60}}]}}]}}]}}'
    )

    try:
        response = await llm.ainvoke(prompt)
        raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
    except Exception:
        logger.exception("LLM failed in create_training_cycle for user %s", telegram_user_id)
        return {"error": "Не удалось создать цикл — ошибка LLM"}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        cycle = json.loads(match.group()) if match else {}
    except json.JSONDecodeError:
        logger.warning("JSON parse failed in create_training_cycle, raw=%r", raw[:200])
        cycle = {}

    if not cycle:
        return {"error": "Не удалось разобрать ответ модели"}

    user_id = await _get_user_id(telegram_user_id)
    if user_id:
        try:
            saved = (
                await client.table("workouts")
                .insert({
                    "user_id": user_id,
                    "title": cycle.get("title", f"Цикл: {goal} {weeks} нед."),
                    "plan": cycle,
                })
                .execute()
            )
            cycle["id"] = saved.data[0]["id"] if saved.data else None
        except Exception:
            logger.exception("Failed to save training cycle for user %s", telegram_user_id)

    return cycle


@tool
async def find_exercises(muscle_group: str, equipment: Optional[str] = None) -> list[dict]:
    """Найти упражнения по группе мышц или типу.

    Args:
        muscle_group: Группа мышц (chest/back/legs/shoulders/arms/core/cardio/flexibility).
        equipment: Доступное оборудование: barbell/dumbbells/bar/none и т.д. (optional).
    """
    from agent.tools.exercise_db import get_safe_exercises

    eq = [equipment] if equipment else None
    results = get_safe_exercises(muscle_group, user_injuries=[], equipment=eq, max_count=20)
    return [
        {
            "name": ex.name,
            "muscle_group": ex.muscle_group,
            "equipment": list(ex.equipment),
            "difficulty": ex.difficulty,
            "description": ex.description,
            "is_compound": ex.is_compound,
        }
        for ex in results
    ]
