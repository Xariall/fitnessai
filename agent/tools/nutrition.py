import logging
from datetime import date, datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)

_ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

_GOAL_ADJUSTMENTS = {
    "lose_weight": -300,
    "gain_muscle": +300,
    "maintain": 0,
}


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
async def calculate_daily_calories(telegram_user_id: int) -> dict:
    """Рассчитать суточную норму КБЖУ по формуле Миффлина-Сан Жеора с учётом цели."""
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
    # Формула Миффлина-Сан Жеора (для мужчины; +5 для женщины замени на -161)
    bmr = 10 * u["weight_kg"] + 6.25 * u["height_cm"] - 5 * u["age"] + 5
    tdee = bmr * _ACTIVITY_MULTIPLIERS.get(u["activity_level"], 1.55)
    target_calories = int(tdee + _GOAL_ADJUSTMENTS.get(u["goal"], 0))

    # Белок: 2 г/кг; жиры: 25% от калорий; углеводы: остаток
    protein = round(u["weight_kg"] * 2.0, 1)
    fat = round(target_calories * 0.25 / 9, 1)
    carbs = round((target_calories - protein * 4 - fat * 9) / 4, 1)

    return {
        "calories": target_calories,
        "protein_g": protein,
        "fat_g": fat,
        "carbs_g": carbs,
    }


@tool
async def generate_nutrition_plan(
    telegram_user_id: int,
    preferences: Optional[str] = None,
) -> dict:
    """Сгенерировать план питания на день с конкретными блюдами.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        preferences: Предпочтения или ограничения (непереносимости, вкусы).
    """
    import json, re
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

    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})

    llm = get_llm()
    pref_text = f"Предпочтения: {preferences}." if preferences else ""
    prompt = (
        f"Составь план питания на день.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {profile.get('goal')}.\n"
        f"Норма: {norms.get('calories')} ккал, белки {norms.get('protein_g')} г, "
        f"жиры {norms.get('fat_g')} г, углеводы {norms.get('carbs_g')} г. {pref_text}\n\n"
        f"Верни JSON-объект вида:\n"
        f'{{"meals": [{{"type": "breakfast", "name": "...", "calories": 400, "protein": 20, "fat": 10, "carbs": 50}}]}}'
    )
    response = await llm.ainvoke(prompt)

    match = re.search(r"\{.*\}", response.content, re.DOTALL)
    try:
        plan = json.loads(match.group()) if match else {"meals": []}
    except json.JSONDecodeError:
        plan = {"meals": []}

    user_id = await _get_user_id(telegram_user_id)
    if user_id:
        await client.table("nutrition_plans").insert(
            {
                "user_id": user_id,
                "target_calories": norms.get("calories", 0),
                "target_protein": norms.get("protein_g", 0),
                "target_fat": norms.get("fat_g", 0),
                "target_carbs": norms.get("carbs_g", 0),
                "plan": plan,
            }
        ).execute()

    return plan


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
    """Записать приём пищи и вернуть дневной итог.

    meal_type: breakfast | lunch | dinner | snack
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return "Пользователь не найден."

    client = await get_client()
    await client.table("food_logs").insert(
        {
            "user_id": user_id,
            "food_name": food_name,
            "meal_type": meal_type,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    summary = await get_daily_nutrition_summary.ainvoke({"telegram_user_id": telegram_user_id})
    consumed = summary.get("consumed", {})
    return (
        f"✅ Записано: {food_name} — {calories} ккал\n"
        f"За сегодня: {consumed.get('calories', 0)} ккал / "
        f"Б {consumed.get('protein', 0)} г / "
        f"Ж {consumed.get('fat', 0)} г / "
        f"У {consumed.get('carbs', 0)} г"
    )


@tool
async def get_daily_nutrition_summary(telegram_user_id: int) -> dict:
    """Получить сводку по питанию за сегодня: потреблено, осталось до нормы, список записей."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {}

    today = date.today().isoformat()
    client = await get_client()
    logs_result = (
        await client.table("food_logs")
        .select("*")
        .eq("user_id", user_id)
        .gte("logged_at", f"{today}T00:00:00")
        .execute()
    )
    logs = logs_result.data or []

    consumed = {
        "calories": sum(r["calories"] for r in logs),
        "protein": round(sum(r["protein"] for r in logs), 1),
        "fat": round(sum(r["fat"] for r in logs), 1),
        "carbs": round(sum(r["carbs"] for r in logs), 1),
    }

    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})
    remaining = {
        "calories": norms.get("calories", 0) - consumed["calories"],
        "protein": round(norms.get("protein_g", 0) - consumed["protein"], 1),
        "fat": round(norms.get("fat_g", 0) - consumed["fat"], 1),
        "carbs": round(norms.get("carbs_g", 0) - consumed["carbs"], 1),
    }

    return {"consumed": consumed, "remaining": remaining, "logs": logs}


@tool
async def get_food_info(food_name: str, weight_grams: Optional[int] = None) -> dict:
    """Получить КБЖУ продукта. Использует встроенную базу или LLM-запрос.

    Args:
        food_name: Название продукта или блюда.
        weight_grams: Вес в граммах (по умолчанию 100 г).
    """
    import json, re
    from llm.provider import get_llm

    grams = weight_grams or 100
    llm = get_llm()
    prompt = (
        f"Дай КБЖУ для \"{food_name}\" на {grams} г.\n"
        f"Верни JSON: {{\"calories\": int, \"protein\": float, \"fat\": float, \"carbs\": float}}\n"
        f"Только JSON, без пояснений."
    )
    response = await llm.ainvoke(prompt)
    match = re.search(r"\{.*?\}", response.content, re.DOTALL)
    try:
        data = json.loads(match.group()) if match else {}
    except json.JSONDecodeError:
        data = {}

    return {**data, "food_name": food_name, "weight_grams": grams}
