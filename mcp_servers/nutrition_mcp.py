"""MCP-сервер: питание, дневник еды, калории, БЖУ."""

import json
import logging
import sys
import os

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastmcp import FastMCP
from database import db

mcp = FastMCP("nutrition", instructions="Сервер для работы с питанием, дневником еды и расчётом калорий.")


def _calculate_nutrition(weight, height, age, gender, activity, goal) -> dict:
    """Mifflin-St Jeor BMR → TDEE → target kcal → macros."""
    if gender == "male":
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

    multipliers = {"sedentary": 1.2, "moderate": 1.375, "active": 1.55, "athlete": 1.725}
    tdee = bmr * multipliers.get(activity, 1.2)

    adjustments = {"lose": 0.85, "gain": 1.15, "maintain": 1.0, "recomposition": 1.0}
    target = tdee * adjustments.get(goal, 1.0)

    protein = weight * 2.0
    fat = weight * 1.0
    carbs = max((target - (protein * 4) - (fat * 9)) / 4, 50.0)

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": round(target),
        "protein_g": round(protein),
        "fat_g": round(fat),
        "carbs_g": round(carbs),
    }


@mcp.tool()
async def search_food(query: str) -> str:
    """Поиск продукта в базе по названию.
    Возвращает калории и БЖУ на 100 г. Пример: search_food('курица')"""
    results = await db.search_food(query)

    if results:
        # Inject source field so the agent knows where data came from
        for r in results:
            r["source"] = "local"
        return json.dumps(results, ensure_ascii=False)

    # Local DB returned nothing — try OpenNutrition API as fallback
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.opennutrition.com/foods/search",
                params={"query": query, "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            # API returns a list of food items; take the first match
            items = data if isinstance(data, list) else data.get("items", data.get("results", []))
            if items:
                item = items[0]
                external = {
                    "name": item["name"],
                    "calories": item["calories"],
                    "protein": item["protein"],
                    "fat": item["fat"],
                    "carbs": item["carbohydrates"],  # rename to match local format
                    "source": "opennutrition",
                }
                return json.dumps([external], ensure_ascii=False)
    except Exception:
        logger.exception("OpenNutrition API fallback failed for query=%r", query)

    return f"Продукт '{query}' не найден ни в локальной базе, ни во внешнем источнике."


@mcp.tool()
async def log_meal(
    user_id: str,
    product_name: str,
    weight_g: float,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
) -> str:
    """Записать приём пищи в дневник.
    Калории и БЖУ указываются уже пересчитанные на фактический вес порции."""
    await db.log_meal(user_id, product_name, weight_g, calories, protein, fat, carbs)
    return f"Записано: {product_name} ({weight_g}г) — {round(calories)} ккал"


@mcp.tool()
async def log_meal_from_base(
    user_id: str, product_name: str, weight_g: float
) -> str:
    """Записать приём пищи, автоматически рассчитав КБЖУ из базы продуктов.
    Ищет продукт по названию, пересчитывает на вес порции."""
    results = await db.search_food(product_name)
    if not results:
        return f"Продукт '{product_name}' не найден. Укажите КБЖУ вручную через log_meal."

    product = results[0]
    ratio = weight_g / 100.0
    cal = round(product["calories"] * ratio, 1)
    prot = round(product["protein"] * ratio, 1)
    f_ = round(product["fat"] * ratio, 1)
    carb = round(product["carbs"] * ratio, 1)

    await db.log_meal(user_id, product["name"], weight_g, cal, prot, f_, carb)
    return (
        f"Записано: {product['name']} ({weight_g}г) — "
        f"{cal} ккал | Б:{prot} Ж:{f_} У:{carb}"
    )


@mcp.tool()
async def get_food_diary(user_id: str, date: str | None = None) -> str:
    """Получить дневник питания за день.
    date — опционально, формат 'YYYY-MM-DD'. Без даты — сегодня."""
    entries = await db.get_food_diary(user_id, date)
    if not entries:
        return "Записей в дневнике за этот день нет."
    return json.dumps(entries, ensure_ascii=False)


@mcp.tool()
async def get_daily_summary(user_id: str, date: str | None = None) -> str:
    """Получить итого калорий и БЖУ за день.
    date — опционально, формат 'YYYY-MM-DD'. Без даты — сегодня."""
    summary = await db.get_daily_summary(user_id, date)
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool()
async def calculate_daily_norm(user_id: str) -> str:
    """Рассчитать дневную норму калорий и БЖУ по профилю пользователя.
    Использует формулу Миффлина-Сан Жеора."""
    user = await db.get_user(user_id)
    if not user:
        return "Профиль пользователя не найден. Создайте профиль сначала."

    required = ["weight", "height", "age", "gender", "activity", "goal"]
    missing = [f for f in required if not user.get(f)]
    if missing:
        return f"В профиле не заполнены: {', '.join(missing)}. Обновите профиль."

    result = _calculate_nutrition(
        user["weight"], user["height"], user["age"],
        user["gender"], user["activity"], user["goal"],
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_nutrition_plan(user_id: int, date: str) -> str:
    """Получить план питания на конкретный день.
    date — формат 'YYYY-MM-DD'. Возвращает план с блюдами по приёмам пищи или null если плана нет."""
    plan = await db.get_nutrition_plan(user_id, date)
    if plan is None:
        return "null"
    return json.dumps(plan, ensure_ascii=False)


@mcp.tool()
async def create_nutrition_plan(
    user_id: int,
    date: str,
    meals_json: str,
    notes: str | None = None,
) -> str:
    """Создать или перезаписать план питания на день.
    date — формат 'YYYY-MM-DD'.
    meals_json — JSON-строка со списком блюд:
      '[{"meal_type":"breakfast","product_name":"Овсянка","weight_g":100,"calories":350,"protein":12,"fat":6,"carbs":60}]'
    meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'.
    Если план на эту дату уже существует — старые блюда удаляются и создаются новые."""
    try:
        meals = json.loads(meals_json)
    except json.JSONDecodeError as e:
        return f"Ошибка: невалидный JSON в meals_json: {e}"
    plan = await db.create_nutrition_plan(
        user_id=user_id,
        date=date,
        meals=meals,
        notes=notes,
        generated_by="agent",
    )
    return json.dumps(plan, ensure_ascii=False)


@mcp.tool()
async def update_plan_item(item_id: int, weight_g: float) -> str:
    """Изменить вес порции блюда в плане питания и пересчитать КБЖУ.
    Ищет продукт в базе food_products для точного пересчёта; если не найден — масштабирует пропорционально."""
    updated = await db.update_plan_item(item_id, weight_g)
    if updated is None:
        return f"Позиция с id={item_id} не найдена."
    return json.dumps(updated, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
