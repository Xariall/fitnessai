import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)

# Встроенная база упражнений
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


async def _get_user_id(telegram_user_id: int) -> Optional[str]:
    client = await get_client()
    result = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None


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
