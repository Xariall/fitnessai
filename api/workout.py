"""Workout programs API: list, get, generate, delete."""

from __future__ import annotations

import json
import logging
import os
import re

import google.genai as genai_sdk
from fastapi import APIRouter, Depends, HTTPException
from google.genai import types as genai_types
from pydantic import BaseModel

from api.auth import get_current_user
from database import db
from database.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workout-programs", tags=["workout"])

# ── Gemini plan generation ────────────────────────────────────────────────────

_DAYS_RU = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_SYSTEM = (
    "Ты персональный тренер. Составляй тренировочные планы строго в формате JSON. "
    "Не добавляй никакого текста, только JSON."
)

_EXERCISE_SCHEMA = (
    '{"name": "string", "description": "string", "sets": number, '
    '"reps": "string (e.g. \\"8-10\\" or \\"12\\")", "weight": "string (e.g. \\"60кг\\" or \\"свой вес\\")", '
    '"rest": "string (e.g. \\"60с\\" or \\"90с\\")"}'
)


def _build_prompt(goal: str, level: str, days: int, injuries: str) -> str:
    active_days = _DAYS_RU[:days] + ["saturday", "sunday"][: max(0, days - 5)]
    # Use first `days` weekdays
    selected = _DAYS_RU[:days]
    rest_days = [d for d in _DAYS_RU if d not in selected]

    injury_note = f"\nУчти травмы/ограничения: {injuries}" if injuries.strip() else ""

    return (
        f"Составь тренировочный план.\n"
        f"Цель: {goal}\n"
        f"Уровень: {level}\n"
        f"Тренировочных дней в неделю: {days}{injury_note}\n\n"
        f"Формат ответа — JSON-объект с ключами для каждого дня недели:\n"
        f"monday, tuesday, wednesday, thursday, friday, saturday, sunday\n\n"
        f"Тренировочные дни ({', '.join(selected)}): массив упражнений.\n"
        f"Дни отдыха ({', '.join(rest_days)}): пустой массив [].\n\n"
        f"Каждое упражнение:\n{_EXERCISE_SCHEMA}\n\n"
        f"Требования:\n"
        f"- 3-5 упражнений в тренировочный день\n"
        f"- Сбалансированная нагрузка по группам мышц\n"
        f"- Реалистичные веса для уровня {level}\n"
        f"- Верни только JSON без markdown блоков"
    )


def _level_label(level: str) -> str:
    return {"beginner": "Начинающий", "intermediate": "Средний", "advanced": "Продвинутый"}.get(
        level.lower(), level
    )


def _goal_to_name(goal: str, level: str) -> str:
    goal_map = {
        "weight_loss": "Программа на похудение",
        "muscle_gain": "Программа на набор массы",
        "maintenance": "Программа поддержания формы",
        "endurance": "Программа на выносливость",
        "strength": "Силовая программа",
    }
    base = goal_map.get(goal, "Персональная программа тренировок")
    level_suffix = {"beginner": " для начинающих", "intermediate": " среднего уровня", "advanced": " для продвинутых"}.get(
        level.lower(), ""
    )
    return base + level_suffix


async def _generate_via_gemini(goal: str, level: str, days: int, injuries: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "GEMINI_API_KEY not configured")

    client = genai_sdk.Client(api_key=api_key)
    prompt = _build_prompt(goal, level, days, injuries)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=f"{_SYSTEM}\n\n{prompt}",
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as exc:
            if attempt < 2:
                import asyncio
                await asyncio.sleep(3 * (2 ** attempt))
            else:
                logger.error("Gemini workout generation failed: %s", exc)
                raise HTTPException(503, "Не удалось сгенерировать план. Попробуйте ещё раз.")

    raw = re.sub(r"```json\s*|```", "", response.text).strip()
    try:
        plan = json.loads(raw)
    except Exception:
        raise HTTPException(500, "Не удалось разобрать ответ от ИИ.")

    # Ensure all 7 days exist
    for day in _DAYS_RU:
        plan.setdefault(day, [])

    return plan


# ── Request bodies ────────────────────────────────────────────────────────────

class GenerateProgramBody(BaseModel):
    days_per_week: int = 3   # 1-7


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_programs(user: User = Depends(get_current_user)) -> list[dict]:
    return await db.get_workout_programs(str(user.id))


@router.get("/active")
async def get_active_program(user: User = Depends(get_current_user)) -> dict | None:
    programs = await db.get_workout_programs(str(user.id))
    if not programs:
        return None
    latest = programs[0]  # already sorted desc by created_at
    latest["program"] = json.loads(latest["program_json"])
    return latest


@router.get("/{program_id}")
async def get_program(program_id: int, user: User = Depends(get_current_user)) -> dict:
    p = await db.get_workout_program_by_id(program_id, user.id)
    if not p:
        raise HTTPException(404, "Program not found")
    p["program"] = json.loads(p["program_json"])
    return p


@router.post("/generate")
async def generate_program(
    body: GenerateProgramBody,
    user: User = Depends(get_current_user),
) -> dict:
    days = max(1, min(7, body.days_per_week))

    goal = user.goal or "maintenance"
    level_raw = user.activity or "beginner"
    # Map activity to training level
    level = "beginner" if level_raw in ("sedentary", "light") else (
        "intermediate" if level_raw in ("moderate",) else "advanced"
    )
    injuries = user.injuries or ""

    plan = await _generate_via_gemini(goal, level, days, injuries)

    name = _goal_to_name(goal, level)
    plan_json = json.dumps(plan, ensure_ascii=False)

    prog_id = await db.save_workout_program(
        str(user.id), name, goal, level, days, plan_json
    )

    return {
        "id": prog_id,
        "name": name,
        "goal": goal,
        "level": level,
        "level_label": _level_label(level),
        "days_per_week": days,
        "program": plan,
        "program_json": plan_json,
    }


@router.delete("/{program_id}")
async def delete_program(program_id: int, user: User = Depends(get_current_user)) -> dict:
    deleted = await db.delete_workout_program(program_id, user.id)
    if not deleted:
        raise HTTPException(404, "Program not found")
    return {"success": True}
