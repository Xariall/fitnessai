"""Nutrition plan endpoints."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date as date_type

import google.genai as genai_sdk
from google.genai import types as genai_types
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

import database.db as db
from api.auth import get_current_user
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class GeneratePlanBody(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field(default="", max_length=1000)


class UpdateItemBody(BaseModel):
    weight_g: float = Field(gt=0, le=5000)


class AddItemBody(BaseModel):
    plan_id: int
    meal_type: str | None = Field(default=None, max_length=20)
    product_name: str = Field(min_length=1, max_length=255)
    weight_g: float = Field(gt=0, le=5000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _genai_client() -> genai_sdk.Client:
    return genai_sdk.Client(api_key=os.getenv("GEMINI_API_KEY"))


async def _generate_meals(daily_norm: dict, notes: str) -> list[dict]:
    """Call Gemini in JSON mode to get a structured meal plan.

    Uses google.genai SDK directly with response_mime_type='application/json'
    so the model is guaranteed to return valid JSON — no regex needed.
    """
    notes_line = f"\nПожелания пользователя: {notes}" if notes.strip() else ""
    prompt = (
        f"Составь план питания на один день. Целевая норма:{notes_line}\n"
        f"- Калории: {daily_norm['target_calories']} ккал\n"
        f"- Белки: {daily_norm['protein_g']} г\n"
        f"- Жиры: {daily_norm['fat_g']} г\n"
        f"- Углеводы: {daily_norm['carbs_g']} г\n\n"
        f"Верни JSON-массив блюд. Каждый элемент:\n"
        f'{{"meal_type":"breakfast","product_name":"Название","weight_g":100,'
        f'"calories":300,"protein":15,"fat":8,"carbs":40}}\n\n'
        f"meal_type только: breakfast, lunch, dinner, snack.\n"
        f"2-3 блюда на breakfast/lunch/dinner, 1-2 на snack. "
        f"Суммарные калории ≈ {daily_norm['target_calories']} ккал."
    )
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _genai_client()
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


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
    """Генерирует план питания через прямой вызов Gemini (без agent loop)."""
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

    try:
        meals = await _generate_meals(daily_norm, body.notes)
    except Exception:
        logger.exception("LLM meal generation failed (user=%s, date=%s)", user.id, body.date)
        raise HTTPException(500, "Не удалось сгенерировать план питания. Попробуйте ещё раз.")

    if not meals:
        raise HTTPException(500, "Модель вернула пустой план. Попробуйте ещё раз.")

    plan = await db.create_nutrition_plan(
        user_id=user.id,
        date=body.date,
        meals=meals,
        notes=body.notes or None,
        generated_by="llm",
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
