"""Nutrition plan endpoints."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Response, status
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import database.db as db
from agent.graph import get_graph
from agent.prompts import SYSTEM_PROMPT
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

def _extract_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b if isinstance(b, str) else b.get("text", "")
            for b in content
            if isinstance(b, (str, dict))
        ) or str(content)
    return str(content)


def _extract_text(response: dict) -> str:
    for msg in reversed(response.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if not getattr(msg, "tool_calls", None):
                return _extract_content(msg.content)
    return ""


async def _run_agent(user_id: int, thread_id: str, prompt: str) -> str:
    graph = await get_graph()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(user_id=str(user_id)), id="system"),
        HumanMessage(content=prompt),
    ]
    config = {"configurable": {"thread_id": thread_id}}
    response = await graph.ainvoke({"messages": messages}, config=config)
    return _extract_text(response)


def _parse_nutrition_json(text: str) -> dict | None:
    """Try to extract {calories, protein, fat, carbs} from agent reply."""
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
    """Запустить агента для генерации плана питания на указанный день."""
    notes_part = f"Пожелания: {body.notes}. " if body.notes.strip() else ""
    prompt = (
        f"Составь план питания на {body.date} для пользователя. "
        f"{notes_part}"
        f"Сначала используй calculate_daily_norm чтобы узнать норму КБЖУ. "
        f"Затем используй create_nutrition_plan чтобы сохранить план. "
        f"Обязательные параметры: user_id={user.id}, date='{body.date}', notes='{body.notes}'. "
        f"Параметр meals_json — это JSON-строка (не список!) со всеми блюдами для приёмов пищи "
        f"breakfast, lunch, dinner, snack. Формат: "
        f'"[{{\\"meal_type\\":\\"breakfast\\",\\"product_name\\":\\"Овсянка\\",\\"weight_g\\":100,'
        f'\\"calories\\":350,\\"protein\\":12,\\"fat\\":6,\\"carbs\\":60}}]". '
        f"Каждое блюдо должно иметь поля: meal_type, product_name, weight_g, calories, protein, fat, carbs."
    )
    # Use a unique thread per attempt so MemorySaver never replays stale messages
    thread_id = f"nutplan_{user.id}_{body.date}_{uuid.uuid4().hex[:8]}"
    try:
        await _run_agent(user.id, thread_id, prompt)
    except Exception:
        logger.exception("Agent error during plan generation")
        raise HTTPException(500, "Ошибка при генерации плана. Попробуйте ещё раз.")

    plan = await db.get_nutrition_plan(user.id, body.date)
    if plan is None:
        raise HTTPException(500, "Агент не сохранил план. Попробуйте ещё раз.")
    daily_norm = await db.calculate_daily_norm(user.id)
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
        # Ask agent to estimate nutrition for 100g and return JSON
        prompt = (
            f"Оцени питательную ценность продукта '{body.product_name}' на 100г. "
            f"Ответь строго в формате JSON без пояснений: "
            f'{{\"calories\": <число>, \"protein\": <число>, \"fat\": <число>, \"carbs\": <число>}}'
        )
        thread_id = f"food_lookup_{user.id}_{body.product_name}"
        try:
            reply = await _run_agent(user.id, thread_id, prompt)
            nutrition = _parse_nutrition_json(reply)
        except Exception:
            logger.exception("Agent food lookup error")
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
