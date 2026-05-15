import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)


@tool
async def calculate_daily_calories(telegram_user_id: int) -> dict:
    """Рассчитать суточную норму КБЖУ по формуле Миффлина-Сан Жеора."""
    client = await get_client()
    result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    if not result.data:
        return {}

    u = result.data
    # Формула Миффлина-Сан Жеора (предполагаем мужчину по умолчанию)
    bmr = 10 * u["weight_kg"] + 6.25 * u["height_cm"] - 5 * u["age"] + 5

    activity_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    tdee = bmr * activity_multipliers.get(u["activity_level"], 1.55)

    goal_adjustments = {
        "lose_weight": -300,
        "gain_muscle": +300,
        "maintain": 0,
    }
    target_calories = int(tdee + goal_adjustments.get(u["goal"], 0))

    return {
        "calories": target_calories,
        "protein": round(u["weight_kg"] * 2.0, 1),
        "fat": round(target_calories * 0.25 / 9, 1),
        "carbs": round((target_calories - u["weight_kg"] * 2.0 * 4 - target_calories * 0.25) / 4, 1),
    }


@tool
async def generate_nutrition_plan(
    telegram_user_id: int,
    preferences: Optional[str] = None,
) -> dict:
    """Сгенерировать план питания на день.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        preferences: Предпочтения или ограничения (непереносимости и т.д.).
    """
    # TODO: реализовать генерацию плана через LLM и сохранить в nutrition_plans
    raise NotImplementedError


@tool
async def log_food(
    telegram_user_id: int,
    food_name: str,
    meal_type: str,
    calories: int,
    protein: float,
    fat: float,
    carbs: float,
) -> str:
    """Записать приём пищи и вернуть дневной итог."""
    # TODO: реализовать сохранение в food_logs
    raise NotImplementedError


@tool
async def get_daily_nutrition_summary(telegram_user_id: int) -> dict:
    """Получить сводку по питанию за сегодня."""
    # TODO: реализовать запрос food_logs за сегодня + сравнение с нормой
    raise NotImplementedError


@tool
async def get_food_info(food_name: str, weight_grams: Optional[int] = None) -> dict:
    """Получить КБЖУ продукта.

    Args:
        food_name: Название продукта или блюда.
        weight_grams: Вес в граммах (optional, по умолчанию 100г).
    """
    # TODO: встроенная база + LLM-фолбэк
    raise NotImplementedError
