"""Gemini-powered weekly meal plan generator."""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from datetime import date, timedelta

import google.genai as genai_sdk
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


def build_products_string(products: list[dict]) -> str:
    """Build a compact product catalogue string for the Gemini prompt.

    Format: "овсянка(360кк,б12,ж7,у63); куриная грудка(165кк,б31,ж4,у0); ..."
    All nutritional values are rounded to int.
    """
    parts = [
        (
            f"{p['name']}"
            f"({int(round(p['calories']))}кк,"
            f"б{int(round(p['protein']))},"
            f"ж{int(round(p['fat']))},"
            f"у{int(round(p['carbs']))})"
        )
        for p in products
    ]
    return "; ".join(parts)


async def gemini_generate_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
) -> dict:
    """Make a single async Gemini call and return the parsed 7-day plan dict.

    Uses response_mime_type='application/json' so the model is guaranteed to
    return valid JSON. Strips any accidental markdown wrapper before parsing.
    """
    target = daily_norm["target_calories"]
    tdee = daily_norm["tdee"]

    if target < tdee * 0.95:
        goal = "похудение"
    elif target > tdee * 1.05:
        goal = "набор массы"
    else:
        goal = "поддержание веса"

    products_str = build_products_string(products)

    system_prompt = (
        "Ты диетолог-ассистент. Составь 7-дневный план питания.\n"
        "Правила:\n"
        "- Используй ТОЛЬКО продукты из списка\n"
        "- Каждый день: breakfast, lunch, dinner, snack\n"
        "- breakfast: 2 продукта, lunch: 3, dinner: 2, snack: 1\n"
        "- Подбери вес порций чтобы сумма КБЖУ за день была близка к цели\n"
        "- Не повторяй один продукт в одном приёме пищи два дня подряд\n"
        "- Ответ ТОЛЬКО валидный JSON без markdown и пояснений"
    )

    user_message = (
        f"Цель: {goal} | КБЖУ/день: {target}ккал, "
        f"Б:{daily_norm['protein_g']}г, Ж:{daily_norm['fat_g']}г, У:{daily_norm['carbs_g']}г\n"
        f"Продукты: {products_str}\n"
        f"Заметки: {notes}"
    )

    # Gemini client is created per-call (project convention — no singleton)
    client = genai_sdk.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = await client.aio.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"{system_prompt}\n\n{user_message}",
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    # Strip markdown wrapper in case the model ignores response_mime_type hint
    clean_text = re.sub(r"```json\s*|```", "", response.text).strip()
    return json.loads(clean_text)


def match_product(name: str, products: list[dict]) -> dict | None:
    """Return the best-matching product dict for a given name.

    Strategy:
      1. Exact case-insensitive match
      2. difflib fuzzy match with cutoff=0.6
      3. None — caller should skip the item
    """
    name_lower = name.lower()

    # 1. Exact match
    for p in products:
        if p["name"].lower() == name_lower:
            return p

    # 2. Fuzzy match
    names_lower = [p["name"].lower() for p in products]
    close = difflib.get_close_matches(name_lower, names_lower, n=1, cutoff=0.6)
    if close:
        product = next(p for p in products if p["name"].lower() == close[0])
        logger.warning("Fuzzy match: %r → %r", name, product["name"])
        return product

    logger.warning("No product match found for: %r", name)
    return None


def calculate_item_kbju(product: dict, weight_g: float) -> dict:
    """Return a meal-item dict with КБЖУ scaled to the given weight.

    All per-100g values from the product are multiplied by weight_g / 100.
    """
    ratio = weight_g / 100.0
    return {
        "product_id":   product["id"],
        "product_name": product["name"],
        "weight_g":     int(round(weight_g)),
        "calories":     round(product["calories"] * ratio, 1),
        "protein":      round(product["protein"] * ratio, 1),
        "fat":          round(product["fat"] * ratio, 1),
        "carbs":        round(product["carbs"] * ratio, 1),
    }


def adjust_day_portions(
    day_items: list[dict],
    target_calories: int,
    tolerance: float = 0.15,
) -> list[dict]:
    """Proportionally scale all portions if the day's total deviates >±15% from target.

    Returns the original list unchanged when within tolerance.
    """
    if not day_items:
        return day_items

    total = sum(item["calories"] for item in day_items)
    if total == 0:
        return day_items

    if abs(total - target_calories) / target_calories <= tolerance:
        return day_items

    scale = target_calories / total
    logger.info(
        "Scaling day portions: %.0f kcal → %.0f kcal (scale=%.3f)",
        total,
        target_calories,
        scale,
    )
    return [
        {
            **item,
            "weight_g": int(round(item["weight_g"] * scale)),
            "calories": round(item["calories"] * scale, 1),
            "protein":  round(item["protein"]  * scale, 1),
            "fat":      round(item["fat"]       * scale, 1),
            "carbs":    round(item["carbs"]     * scale, 1),
        }
        for item in day_items
    ]


async def generate_weekly_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
) -> list[dict]:
    """Orchestrate a 7-day meal plan generation via Gemini.

    Steps:
      1. Call Gemini to get structured JSON for 7 days.
      2. For each day's meal items, fuzzy-match to DB products.
      3. Calculate КБЖУ for each matched item.
      4. Adjust day portions to stay within ±15% of the daily calorie target.
      5. Return a flat list of all items across all 7 days.

    Each returned item has:
        product_id, product_name, weight_g, calories, protein, fat, carbs,
        meal_type, plan_date
    """
    result = await gemini_generate_plan(daily_norm, products, notes)
    today = date.today()
    all_items: list[dict] = []

    for day in result.get("days", []):
        day_number: int = day["day"]
        plan_date = today + timedelta(days=day_number - 1)
        day_items: list[dict] = []

        for meal in day.get("meals", []):
            meal_type: str = meal["meal_type"]

            for raw_item in meal.get("items", []):
                product = match_product(raw_item["product_name"], products)
                if product is None:
                    logger.warning(
                        "Skipping unmatched item %r (day=%d, meal=%s)",
                        raw_item["product_name"],
                        day_number,
                        meal_type,
                    )
                    continue

                kbju = calculate_item_kbju(product, float(raw_item["weight_g"]))
                day_items.append({**kbju, "meal_type": meal_type, "plan_date": plan_date})

        adjusted = adjust_day_portions(day_items, daily_norm["target_calories"])
        all_items.extend(adjusted)

    return all_items
