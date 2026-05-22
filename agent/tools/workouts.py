import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)

_EXERCISE_DB: list[dict] = [
    {"name": "Приседания", "muscle_group": "legs", "equipment": "none", "description": "Базовое упражнение на квадрицепсы и ягодицы."},
    {"name": "Жим штанги лёжа", "muscle_group": "chest", "equipment": "barbell", "description": "Базовое упражнение на грудь."},
    {"name": "Становая тяга", "muscle_group": "back", "equipment": "barbell", "description": "Базовое упражнение на спину и заднюю цепь."},
    {"name": "Подтягивания", "muscle_group": "back", "equipment": "bar", "description": "Упражнение на широчайшие мышцы спины."},
    {"name": "Отжимания", "muscle_group": "chest", "equipment": "none", "description": "Упражнение на грудь без оборудования."},
    {"name": "Выпады", "muscle_group": "legs", "equipment": "none", "description": "Упражнение на ноги и ягодицы."},
    {"name": "Жим гантелей сидя", "muscle_group": "shoulders", "equipment": "dumbbells", "description": "Упражнение на дельтовидные мышцы."},
    {"name": "Сгибания на бицепс", "muscle_group": "biceps", "equipment": "dumbbells", "description": "Изолирующее упражнение на бицепс."},
    {"name": "Французский жим", "muscle_group": "triceps", "equipment": "barbell", "description": "Изолирующее упражнение на трицепс."},
    {"name": "Планка", "muscle_group": "core", "equipment": "none", "description": "Упражнение на стабилизацию кора."},
    {"name": "Скручивания", "muscle_group": "core", "equipment": "none", "description": "Упражнение на пресс."},
    {"name": "Бег", "muscle_group": "cardio", "equipment": "none", "description": "Кардио упражнение."},
    {"name": "Велосипед", "muscle_group": "cardio", "equipment": "bike", "description": "Кардио на велотренажёре или велосипеде."},
    {"name": "Прыжки на скакалке", "muscle_group": "cardio", "equipment": "rope", "description": "Высокоинтенсивное кардио."},
    {"name": "Растяжка квадрицепса", "muscle_group": "flexibility", "equipment": "none", "description": "Растяжка передней поверхности бедра."},
    {"name": "Растяжка спины (кошка-корова)", "muscle_group": "flexibility", "equipment": "none", "description": "Мобилизация позвоночника."},
]


@tool
async def generate_workout_plan(
    telegram_user_id: int,
    focus: str,
    duration_minutes: int,
) -> dict:
    """Сгенерировать план тренировки на основе профиля пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        focus: Группа мышц или тип (chest/back/legs/shoulders/arms/core/cardio/strength/flexibility).
        duration_minutes: Длительность тренировки в минутах.
    """
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

    llm = get_llm()
    prompt = (
        f"Составь план тренировки.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, рост {profile.get('height_cm')} см, "
        f"цель: {profile.get('goal')}, активность: {profile.get('activity_level')}.\n"
        f"Фокус: {focus}. Длительность: {duration_minutes} минут.\n\n"
        f"Верни JSON-объект вида:\n"
        f'{{"title": "...", "exercises": [{{"name": "...", "sets": 3, "reps": "10-12", "rest_seconds": 60}}]}}'
    )
    import json, re

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

    user_id = await _get_user_id(telegram_user_id)
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
async def log_workout(
    telegram_user_id: int,
    notes: str,
    workout_id: Optional[str] = None,
) -> str:
    """Записать выполненную тренировку."""
    from datetime import datetime, timezone

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
    from datetime import datetime, timedelta, timezone

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"can_train": True, "status": "ready", "message": "Нет данных о тренировках — начинай!"}

    client = await get_client()
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
            "message": f"Последние 48 часов без тренировок. Готов к работе 💪",
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

    llm = get_llm()
    prompt = (
        f"Составь мезоцикл тренировок на {weeks} недель.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
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
        muscle_group: Группа мышц (chest/back/legs/shoulders/biceps/triceps/core/cardio/flexibility).
        equipment: Доступное оборудование: barbell/dumbbells/bar/none и т.д. (optional).
    """
    results = [
        ex for ex in _EXERCISE_DB
        if muscle_group.lower() in ex["muscle_group"].lower()
    ]
    if equipment:
        results = [ex for ex in results if equipment.lower() in ex["equipment"].lower()]
    return results
