"""Генерация разовой тренировки и поиск упражнений."""
import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _enrich_exercises_with_ru, _get_recent_plan, _normalize_key, _parse_reps

logger = logging.getLogger(__name__)


@tool
async def generate_workout_plan(
    telegram_user_id: int,
    focus: str,
    duration_minutes: int,
    equipment: Optional[str] = None,
) -> dict:
    """Сгенерировать план тренировки на основе профиля пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        focus: Группа мышц или тип (chest/back/legs/shoulders/arms/core/cardio/strength/flexibility).
        duration_minutes: Длительность тренировки в минутах.
        equipment: Доступное оборудование. Передай 'none' для тренировки только с весом тела (дома, без инвентаря).
                   Варианты: none / barbell / dumbbells / cable / machine / bands / kettlebells.
                   Если не указано — будут предложены упражнения с любым инвентарём.
    """
    import json
    import re

    from agent.tools.exercise_db import get_safe_exercises
    from llm.provider import get_llm

    profile = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    ) or {}
    injuries: list[str] = profile.get("injuries") or []

    user_id = await _get_user_id(telegram_user_id)

    # Check for a recent workout with the same focus for progressive overload
    progressive_note = ""
    if user_id:
        recent = await _get_recent_plan(user_id, focus, days=7)
        if recent and recent.get("last_performance") and not recent.get("last_done_as_planned"):
            perf_by_key = {_normalize_key(ex["name"]): ex for ex in recent["last_performance"]}
            lines = []
            for planned_ex in recent.get("plan_exercises", []):
                key = _normalize_key(planned_ex.get("name", ""))
                actual = perf_by_key.get(key)
                if actual:
                    lo, hi = _parse_reps(planned_ex.get("reps", "8"))
                    reps_done = actual.get("reps_done") or 0
                    weight = actual.get("weight_kg")
                    if weight is not None:
                        note = "увеличь вес" if reps_done >= hi else "тот же вес"
                        lines.append(f"- {planned_ex['name']}: {weight}кг × {reps_done} → {note}")
            if lines:
                progressive_note = (
                    f"ПРОГРЕССИЯ (на основе прошлой тренировки '{recent['title']}'):\n"
                    + "\n".join(lines)
                )
            else:
                progressive_note = (
                    f"ВАЖНО — ПРОГРЕССИЯ: недавно пользователь делал тренировку '{recent['title']}'. "
                    f"Упражнения были: {recent['exercises_summary']}. "
                    f"Используй те же упражнения и добавь прогрессию: +5–10% веса или +1–2 повторения."
                )
        elif recent:
            progressive_note = (
                f"ВАЖНО — ПРОГРЕССИЯ: недавно пользователь делал тренировку '{recent['title']}'. "
                f"Упражнения были: {recent['exercises_summary']}. "
                f"Используй те же упражнения и добавь прогрессию: +5–10% веса или +1–2 повторения."
            )
        else:
            progressive_note = (
                "Нет истории. Оцени стартовый вес по профилю: "
                f"вес тела {profile.get('weight_kg')}кг, цель {profile.get('goal')}, "
                f"активность {profile.get('activity_level')}. "
                "Ориентиры для начинающего: жим лёжа ≈ 40–50% веса тела, "
                "приседания ≈ 50–60%, становая ≈ 60–70%, изолирующие ≈ 15–30%."
            )

    # Filter safe exercises in Python — no LLM needed for this step
    eq_filter = [equipment] if equipment else None
    safe = get_safe_exercises(focus, injuries, equipment=eq_filter, max_count=15)
    if not safe:
        return {
            "title": f"Тренировка: {focus}",
            "exercises": [],
            "error": (
                f"Нет доступных упражнений для группы '{focus}' "
                f"с учётом противопоказаний. Попробуй другую группу мышц."
            ),
        }

    exercises_context = "\n".join(
        f"- {ex.name}: {ex.description}" for ex in safe
    )

    llm = get_llm()
    prompt = (
        f"Составь план тренировки.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, рост {profile.get('height_cm')} см, "
        f"цель: {profile.get('goal')}, активность: {profile.get('activity_level')}.\n"
        f"Фокус: {focus}. Длительность: {duration_minutes} минут.\n"
        f"{progressive_note}\n\n"
        f"Используй ТОЛЬКО упражнения из этого списка (выбери 4–6 подходящих):\n"
        f"{exercises_context}\n\n"
        f"Верни JSON:\n"
        f'{{"title": "...", "exercises": [{{"name": "...", "sets": 3, "reps": "8-10", "weight_kg": 60, "rest_seconds": 90}}]}}'
    )

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

    if user_id:
        try:
            saved = await fetchrow(
                "INSERT INTO workouts (user_id, title, plan) VALUES ($1, $2, $3) RETURNING id",
                user_id, plan.get("title", focus), plan,
            )
            plan["id"] = saved["id"] if saved else None
        except Exception:
            logger.exception("Failed to save workout to DB for user %s", telegram_user_id)

    # Estimate duration and calorie burn from exercise data
    exercises = plan.get("exercises") or []
    if exercises:
        total_seconds = sum(
            ex.get("sets", 3) * (30 + ex.get("rest_seconds", 90))
            for ex in exercises
        )
        est_duration = round(10 + total_seconds / 60)
        weight_kg = profile.get("weight_kg") or 75
        plan["estimated_duration_min"] = est_duration
        plan["estimated_calories"] = round(weight_kg * 0.0875 * est_duration)
    else:
        plan["estimated_duration_min"] = None
        plan["estimated_calories"] = None

    plan["exercises"] = _enrich_exercises_with_ru(plan.get("exercises") or [])
    return plan


@tool
async def find_exercises(muscle_group: str, equipment: Optional[str] = None) -> list[dict]:
    """Найти упражнения по группе мышц или типу.

    Args:
        muscle_group: Группа мышц (chest/back/legs/shoulders/arms/core/cardio/flexibility).
        equipment: Доступное оборудование: barbell/dumbbells/bar/none и т.д. (optional).
    """
    from agent.tools.exercise_db import get_safe_exercises

    eq = [equipment] if equipment else None
    results = get_safe_exercises(muscle_group, user_injuries=[], equipment=eq, max_count=20)
    return [
        {
            "name": ex.name,
            "muscle_group": ex.muscle_group,
            "equipment": list(ex.equipment),
            "difficulty": ex.difficulty,
            "description": ex.description,
            "is_compound": ex.is_compound,
        }
        for ex in results
    ]
