"""Nutrition plan endpoints."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from datetime import date as date_type

import google.genai as genai_sdk
from google.genai import types as genai_types
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

import database.db as db
from api.auth import get_current_user
from app.services.nutrition_planner import filter_excluded_products, generate_weekly_plan
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


# ── Schemas ───────────────────────────────────────────────────────────────────

_VALID_MEAL_TYPES = frozenset({"breakfast", "lunch", "dinner", "snack"})
_DEFAULT_MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


class GeneratePlanBody(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field(default="", max_length=1000)
    meal_types: list[str] = Field(default_factory=lambda: list(_DEFAULT_MEAL_TYPES))

    @property
    def valid_meal_types(self) -> list[str]:
        """Return only known meal types in canonical order."""
        order = list(_DEFAULT_MEAL_TYPES)
        seen = [m for m in order if m in self.meal_types]
        return seen or list(_DEFAULT_MEAL_TYPES)


class UpdateItemBody(BaseModel):
    weight_g: float = Field(gt=0, le=5000)


class ToggleConsumedBody(BaseModel):
    consumed: bool


class AddItemBody(BaseModel):
    plan_id: int
    meal_type: str | None = Field(default=None, max_length=20)
    product_name: str = Field(min_length=1, max_length=255)
    weight_g: float = Field(gt=0, le=5000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _genai_client() -> genai_sdk.Client:
    return genai_sdk.Client(api_key=os.getenv("GEMINI_API_KEY"))


# legacy — single-day Gemini prompt, replaced by generate_weekly_plan() in nutrition_planner.py
# async def _generate_meals(daily_norm: dict, notes: str) -> list[dict]:
#     notes_line = f"\nПожелания пользователя: {notes}" if notes.strip() else ""
#     prompt = (
#         f"Составь план питания на один день. Целевая норма:{notes_line}\n"
#         f"- Калории: {daily_norm['target_calories']} ккал\n"
#         f"- Белки: {daily_norm['protein_g']} г\n"
#         f"- Жиры: {daily_norm['fat_g']} г\n"
#         f"- Углеводы: {daily_norm['carbs_g']} г\n\n"
#         f"Верни JSON-массив блюд. Каждый элемент:\n"
#         f'{{"meal_type":"breakfast","product_name":"Название","weight_g":100,'
#         f'"calories":300,"protein":15,"fat":8,"carbs":40}}\n\n'
#         f"meal_type только: breakfast, lunch, dinner, snack.\n"
#         f"2-3 блюда на breakfast/lunch/dinner, 1-2 на snack. "
#         f"Суммарные калории ≈ {daily_norm['target_calories']} ккал."
#     )
#     client = _genai_client()
#     response = await client.aio.models.generate_content(
#         model="gemini-2.0-flash",
#         contents=prompt,
#         config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
#     )
#     return json.loads(response.text)


# Base fractions and category templates per meal type
_ALGO_MEAL_BASE_FRACTIONS: dict[str, float] = {
    "breakfast": 0.25,
    "lunch":     0.35,
    "dinner":    0.30,
    "snack":     0.10,
}


# algorithmic fallback — used when Gemini is unavailable
async def _generate_meals_algorithmic(
    daily_norm: dict,
    notes: str,  # noqa: ARG001
    foods: list[dict] | None = None,
    meal_types: list[str] | None = None,
) -> list[dict]:
    """Build a meal plan deterministically from the food_products table.

    Products are classified by their macro profile and selected with
    random.choice. Portion weights are back-calculated so each meal
    hits its target calorie fraction.

    Args:
        daily_norm:  Output of db.calculate_daily_norm — contains
                     'target_calories', 'protein_g', 'fat_g', 'carbs_g'.
        notes:       User preferences string — not used in algorithmic path,
                     exclusions are applied by the caller via filter_excluded_products.
        foods:       Pre-filtered product list. If None, all foods are loaded from DB.
        meal_types:  Which meal types to include. Defaults to all four.
                     Calorie fractions are renormalized to always sum to 1.
    """
    if foods is None:
        foods = await db.get_all_foods()
    if not foods:
        raise HTTPException(
            status_code=422,
            detail="База продуктов пуста, обратитесь к администратору",
        )

    active_meals = meal_types or list(_DEFAULT_MEAL_TYPES)

    # Classify products by macro profile (a product can be in multiple lists)
    protein_foods = [f for f in foods if f["protein"] >= 15]
    carb_foods    = [f for f in foods if f["carbs"] >= 40]
    veggies       = [f for f in foods if f["calories"] < 50]

    # Fallback: use full list if a category is empty
    if not protein_foods: protein_foods = foods
    if not carb_foods:    carb_foods = foods
    if not veggies:       veggies = foods

    target = daily_norm["target_calories"]

    # Renormalize fractions so they always sum to 1 regardless of which meals are selected
    raw_fractions = {m: _ALGO_MEAL_BASE_FRACTIONS.get(m, 0.25) for m in active_meals}
    total_fraction = sum(raw_fractions.values()) or 1.0
    fractions = {m: f / total_fraction for m, f in raw_fractions.items()}

    # Categories per meal type
    def _meal_categories(meal_type: str) -> list[list[dict]]:
        if meal_type == "breakfast":
            return [carb_foods, protein_foods]
        if meal_type == "lunch":
            return [protein_foods, carb_foods, veggies]
        if meal_type == "dinner":
            return [protein_foods, veggies]
        if meal_type == "snack":
            return [random.choice([protein_foods, carb_foods])]
        return [protein_foods]

    # meal_type → (fraction_of_daily_target, [list_of_category_lists])
    meal_structure: list[tuple[str, float, list[list[dict]]]] = [
        (m, fractions[m], _meal_categories(m))
        for m in active_meals
    ]

    meals: list[dict] = []
    for meal_type, fraction, categories in meal_structure:
        meal_calories = target * fraction
        num_items = len(categories)
        item_calories = meal_calories / num_items

        for category in categories:
            product = random.choice(category)
            # Avoid division by zero for zero-calorie products
            cal_per_100 = product["calories"] if product["calories"] > 0 else 1.0
            weight_g = (item_calories / cal_per_100) * 100

            # Clamp portion weight to sane limits based on macro profile
            # Order matters: first match wins
            if product["fat"] >= 15:
                min_g, max_g = 10, 50        # nuts, oils
            elif product["protein"] >= 15:
                min_g, max_g = 50, 300       # meat, fish, eggs
            elif product["carbs"] >= 40:
                min_g, max_g = 30, 200       # grains, legumes
            elif product["calories"] < 50:
                min_g, max_g = 50, 300       # vegetables
            else:
                min_g, max_g = 50, 400       # default fallback
            weight_g = max(min_g, min(weight_g, max_g))

            ratio = weight_g / 100.0

            meals.append({
                "meal_type":    meal_type,
                "product_name": product["name"],
                "weight_g":     int(round(weight_g, 0)),
                "calories":     round(product["calories"] * ratio, 1),
                "protein":      round(product["protein"]  * ratio, 1),
                "fat":          round(product["fat"]      * ratio, 1),
                "carbs":        round(product["carbs"]    * ratio, 1),
            })

    total_cal = sum(m["calories"] for m in meals)
    logger.info("Algorithmic plan built: %d meals, %.0f kcal total", len(meals), total_cal)
    return meals


def _parse_nutrition_json(text: str) -> dict | None:
    """Try to extract {calories, protein, fat, carbs} from LLM reply."""
    try:
        match = re.search(r"\{[^{}]*\"calories\"[^{}]*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "calories": float(data["calories"]),
                "protein": float(data["protein"]),
                "fat": float(data["fat"]),
                "carbs": float(data["carbs"]),
            }
    except Exception:
        pass
    return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/debug-genai")
async def debug_genai() -> dict:
    """Диагностика: проверить доступность google.genai и API-ключ."""
    try:
        client = _genai_client()
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents='Return this JSON exactly: {"ok": true}',
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return {"status": "ok", "response_text": response.text}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)[:500]}


@router.get("/plan")
async def get_plan(
    date: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    """Получить план питания за день вместе с дневной нормой КБЖУ."""
    target_date = date or date_type.today().isoformat()
    plan = await db.get_nutrition_plan(user.id, target_date)
    daily_norm = await db.calculate_daily_norm(user.id)
    return {"plan": plan, "daily_norm": daily_norm}


@router.post("/plan/generate")
async def generate_plan(
    body: GeneratePlanBody,
    user: User = Depends(get_current_user),
) -> dict:
    """Генерирует 7-дневный план питания через Gemini; при сбое — алгоритмический fallback."""
    # Pre-check: profile must be complete
    daily_norm = await db.calculate_daily_norm(user.id)
    if daily_norm is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Для генерации плана питания заполните профиль: "
                "вес, рост, возраст, пол, уровень активности и цель."
            ),
        )

    products = await db.get_all_foods()
    meal_types = body.valid_meal_types

    # ── Generation: Gemini → algorithmic fallback ──────────────────────────────
    weekly: bool = False
    try:
        meals = await generate_weekly_plan(daily_norm, products, body.notes, meal_types=meal_types)
        weekly = True
    except Exception as exc:
        logger.warning(
            "Gemini meal generation failed (user=%s), falling back to algorithmic: %s",
            user.id, exc,
        )
        try:
            fallback_products = filter_excluded_products(body.notes, products)
            meals = await _generate_meals_algorithmic(
                daily_norm, body.notes, fallback_products, meal_types=meal_types
            )
        except Exception as fallback_exc:
            logger.exception("Fallback algorithmic generation also failed (user=%s)", user.id)
            raise HTTPException(
                500, f"Ошибка генерации: {type(fallback_exc).__name__}: {fallback_exc}"
            )

    if not meals:
        raise HTTPException(500, "Модель вернула пустой план. Попробуйте ещё раз.")

    # ── Persist ────────────────────────────────────────────────────────────────
    if weekly:
        # Group by plan_date and save each day separately
        meals_by_date: dict[str, list[dict]] = {}
        for item in meals:
            key = (
                item["plan_date"].isoformat()
                if hasattr(item["plan_date"], "isoformat")
                else str(item["plan_date"])
            )
            meals_by_date.setdefault(key, []).append(item)

        for plan_date_str, day_meals in meals_by_date.items():
            await db.create_nutrition_plan(
                user_id=user.id,
                date=plan_date_str,
                meals=day_meals,
                notes=body.notes or None,
                generated_by="gemini",
            )

        # Return the plan for the requested date (first day if not in range)
        plan = await db.get_nutrition_plan(user.id, body.date)
        if plan is None and meals_by_date:
            first_date = sorted(meals_by_date.keys())[0]
            plan = await db.get_nutrition_plan(user.id, first_date)
    else:
        plan = await db.create_nutrition_plan(
            user_id=user.id,
            date=body.date,
            meals=meals,
            notes=body.notes or None,
            generated_by="algorithmic",
        )

    return {"plan": plan, "daily_norm": daily_norm}


@router.patch("/plan/item/{item_id}")
async def patch_item(
    item_id: int,
    body: UpdateItemBody,
    user: User = Depends(get_current_user),
) -> dict:
    """Изменить вес порции и пересчитать КБЖУ."""
    updated = await db.update_plan_item(item_id, body.weight_g)
    if updated is None:
        raise HTTPException(404, "Позиция не найдена.")
    return updated


@router.patch("/plan/item/{item_id}/consumed")
async def toggle_consumed(
    item_id: int,
    body: ToggleConsumedBody,
    user: User = Depends(get_current_user),
) -> dict:
    """Отметить блюдо как съеденное / не съеденное."""
    updated = await db.toggle_plan_item_consumed(item_id, body.consumed)
    if updated is None:
        raise HTTPException(404, "Позиция не найдена.")
    return updated


@router.post("/plan/item", status_code=status.HTTP_201_CREATED)
async def add_item(
    body: AddItemBody,
    user: User = Depends(get_current_user),
) -> dict:
    """Добавить блюдо в план питания. КБЖУ рассчитывается из базы продуктов.
    Если продукт не найден — агент оценивает питательную ценность."""
    foods = await db.search_food(body.product_name)

    if foods:
        food = foods[0]
        ratio = body.weight_g / 100.0
        calories = round(food["calories"] * ratio, 1)
        protein = round(food["protein"] * ratio, 1)
        fat = round(food["fat"] * ratio, 1)
        carbs = round(food["carbs"] * ratio, 1)
    else:
        # Ask LLM in JSON mode to estimate nutrition for 100g
        prompt = (
            f"Оцени питательную ценность продукта '{body.product_name}' на 100г. "
            f"Верни JSON-объект: "
            f'{{"calories": число, "protein": число, "fat": число, "carbs": число}}'
        )
        try:
            client = _genai_client()
            resp = await client.aio.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            nutrition = _parse_nutrition_json(resp.text)
        except Exception:
            logger.exception("LLM food lookup error for %r", body.product_name)
            nutrition = None

        if nutrition:
            # Store in food_products for future use
            try:
                await db.create_food_product(
                    name=body.product_name,
                    calories=nutrition["calories"],
                    protein=nutrition["protein"],
                    fat=nutrition["fat"],
                    carbs=nutrition["carbs"],
                )
            except Exception:
                logger.warning("Failed to save food product to db", exc_info=True)
            ratio = body.weight_g / 100.0
            calories = round(nutrition["calories"] * ratio, 1)
            protein = round(nutrition["protein"] * ratio, 1)
            fat = round(nutrition["fat"] * ratio, 1)
            carbs = round(nutrition["carbs"] * ratio, 1)
        else:
            raise HTTPException(
                404,
                f"Продукт '{body.product_name}' не найден в базе. "
                "Уточните название или используйте чат для записи.",
            )

    return await db.add_meal_plan_item(
        plan_id=body.plan_id,
        meal_type=body.meal_type,
        product_name=body.product_name,
        weight_g=body.weight_g,
        calories=calories,
        protein=protein,
        fat=fat,
        carbs=carbs,
    )


@router.delete("/plan/item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
) -> Response:
    """Удалить позицию из плана питания."""
    deleted = await db.delete_meal_plan_item(item_id)
    if not deleted:
        raise HTTPException(404, "Позиция не найдена.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/diary")
async def get_diary(
    date: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    """Получить дневник питания и итого КБЖУ за день."""
    target_date = date or date_type.today().isoformat()
    entries = await db.get_food_diary(str(user.id), target_date)
    summary = await db.get_daily_summary(str(user.id), target_date)
    return {"entries": entries, "summary": summary}
