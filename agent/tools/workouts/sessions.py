"""Контент следующей тренировочной сессии: генерация по циклу и замена упражнения."""
import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import execute, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _enrich_exercises_with_ru, _get_active_cycle_data, _get_recent_plan, _normalize_key, _parse_reps

logger = logging.getLogger(__name__)


@tool
async def get_next_session_plan(
    telegram_user_id: int,
    duration_minutes: int = 45,
    equipment: Optional[str] = None,
) -> dict:
    """Получить план следующей тренировки по активному циклу.

    Если активного цикла нет — генерирует разовую тренировку через get_recovery_overview.
    Если цикл есть — берёт фокус текущей сессии и передаёт контекст фазы в генерацию.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        duration_minutes: Длительность тренировки в минутах (по умолчанию 45).
        equipment: Оборудование (none / barbell / dumbbells / cable / machine / bands / kettlebells).
    """
    import json
    import re

    from agent.tools.exercise_db import get_safe_exercises
    from llm.provider import get_llm

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    profile = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    ) or {}
    injuries: list[str] = profile.get("injuries") or []

    # Get active cycle
    cycle_row = await _get_active_cycle_data(user_id)
    cycle_context: dict | None = None
    focus = "strength"
    cycle_id: str | None = None

    if cycle_row:
        try:
            week_data = cycle_row["schedule"]["weeks"][cycle_row["current_week"] - 1]
            session_data = week_data["sessions"][cycle_row["current_session_index"]]
            focus = session_data.get("focus", "strength")
            cycle_id = str(cycle_row["id"])
            cycle_context = {
                "cycle_id": cycle_id,
                "title": cycle_row["title"],
                "current_week": cycle_row["current_week"],
                "total_weeks": cycle_row["total_weeks"],
                "phase": week_data.get("phase", "accumulation"),
                "week_theme": week_data.get("theme", ""),
                "session_label": session_data.get("label", ""),
                "session_number_in_week": cycle_row["current_session_index"] + 1,
            }
        except (IndexError, KeyError, TypeError) as exc:
            logger.error(
                "get_next_session_plan: corrupted schedule cycle_id=%s: %s",
                cycle_row.get("id"),
                exc,
            )
            cycle_context = None

    # Build progressive overload note
    progressive_note = ""
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
        elif recent:
            progressive_note = (
                f"ВАЖНО — ПРОГРЕССИЯ: недавно пользователь делал '{recent['title']}'. "
                f"Упражнения: {recent['exercises_summary']}. +5–10% веса или +1–2 повторения."
            )
    elif not recent:
        progressive_note = (
            "Нет истории. Оцени стартовый вес по профилю: "
            f"вес тела {profile.get('weight_kg')}кг, цель {profile.get('goal')}, "
            f"активность {profile.get('activity_level')}."
        )

    # Phase-specific prompt injection
    phase_note = ""
    if cycle_context:
        phase = cycle_context["phase"]
        phase_map = {
            "accumulation":    "4–5 подходов, 70–75% 1RM, повторения 10–12",
            "intensification": "3–4 подхода, 80–85% 1RM, повторения 5–8",
            "deload":          "2–3 подхода, -30% от прошлого веса, повторения 12–15",
        }
        phase_note = (
            f"\nКОНТЕКСТ ЦИКЛА (Неделя {cycle_context['current_week']} из "
            f"{cycle_context['total_weeks']} · {cycle_context['week_theme']}):\n"
            f"Фаза: {phase} → {phase_map.get(phase, '')}\n"
            f"Фокус: {cycle_context['session_label']}\n"
        )

    from agent.prompts.system import TRAINING_METHODOLOGY

    cycle_equipment = (cycle_row.get("equipment") if cycle_row else None) or equipment or "gym"
    cycle_training_type = (cycle_row.get("training_type") if cycle_row else None) or "mixed"

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"Травмы пользователя: {listed}. Строго следуй правилам п.5 методологии.\n"

    eq_filter = [equipment] if equipment else None
    safe = get_safe_exercises(focus, injuries, equipment=eq_filter, max_count=15)
    if not safe:
        return {
            "title": f"Тренировка: {focus}",
            "exercises": [],
            "error": (
                f"Нет доступных упражнений для группы '{focus}' с учётом противопоказаний."
            ),
        }

    exercises_context = "\n".join(f"- {ex.name}: {ex.description}" for ex in safe)

    llm = get_llm()
    prompt = (
        f"{TRAINING_METHODOLOGY}\n\n"
        f"---\n"
        f"ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:\n"
        f"Вес: {profile.get('weight_kg')} кг, рост: {profile.get('height_cm')} см\n"
        f"Цель: {profile.get('goal')}, активность: {profile.get('activity_level')}\n"
        f"Оборудование: {cycle_equipment}\n"
        f"Стиль тренинга: {cycle_training_type}\n"
        f"{injuries_note}"
        f"{phase_note}\n"
        f"{progressive_note}\n\n"
        f"Фокус сессии: {focus}. Длительность: {duration_minutes} минут.\n"
        f"Используй ТОЛЬКО упражнения из этого списка (выбери 4–6 подходящих):\n"
        f"{exercises_context}\n\n"
        f"Верни JSON:\n"
        f'{{"title": "...", "exercises": [{{"name": "...", "sets": 3, "reps": "8-10", "weight_kg": 60, "rest_seconds": 90}}]}}'
    )

    raw = ""
    for attempt in range(3):
        try:
            response = await llm.ainvoke(prompt)
            raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
            break
        except Exception as exc:
            is_retryable = "503" in str(exc) or "unavailable" in str(exc).lower() or "quota" in str(exc).lower()
            if is_retryable and attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt)
                logger.warning("get_next_session_plan: retrying LLM (attempt %d) for user %s", attempt + 1, telegram_user_id)
                continue
            logger.exception("LLM call failed in get_next_session_plan for user %s", telegram_user_id)
            return {"title": f"Тренировка: {focus}", "exercises": [], "error": "Ошибка генерации плана"}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        plan = json.loads(match.group()) if match else {"title": f"Тренировка: {focus}", "exercises": []}
    except json.JSONDecodeError:
        logger.warning("JSON parse failed in get_next_session_plan, raw=%r", raw[:200])
        plan = {"title": f"Тренировка: {focus}", "exercises": []}

    try:
        saved = await fetchrow(
            "INSERT INTO workouts (user_id, title, plan) VALUES ($1, $2, $3) RETURNING id",
            user_id, plan.get("title", focus), plan,
        )
        plan["id"] = saved["id"] if saved else None
    except Exception:
        logger.exception("Failed to save workout in get_next_session_plan for user %s", telegram_user_id)

    if cycle_context:
        plan["cycle_context"] = cycle_context
        plan["cycle_id"] = cycle_id

    # Estimate duration and calorie burn
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
async def replace_workout_exercise(
    telegram_user_id: int,
    old_exercise_name: str,
    new_exercise_name: Optional[str] = None,
    workout_id: Optional[str] = None,
) -> dict:
    """Заменить одно упражнение в последнем (или указанном) плане тренировки.

    Используй когда пользователь говорит «замени X», «не могу делать X», «убери X»,
    «поставь вместо X что-нибудь другое». Сохраняет количество подходов, повторений
    и отдых от оригинала.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        old_exercise_name: Название упражнения которое нужно заменить.
        new_exercise_name: Конкретное новое упражнение (если пользователь уже назвал).
                           Если не указано — подберём автоматически из базы.
        workout_id: ID плана тренировки. Если не указан — берётся последний план.
    """
    from agent.tools.exercise_db import EXERCISE_DB, get_safe_exercises

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # Load workout plan
    if workout_id:
        row = await fetchrow(
            "SELECT id, plan FROM workouts WHERE id = $1 AND user_id = $2",
            workout_id, user_id,
        )
    else:
        row = await fetchrow(
            "SELECT id, plan FROM workouts WHERE user_id = $1 "
            "ORDER BY created_at DESC LIMIT 1",
            user_id,
        )

    if not row:
        return {"error": "Нет сохранённых тренировок"}

    plan = row.get("plan") or {}
    exercises: list[dict] = plan.get("exercises") or []
    if not exercises:
        return {
            "error": "no_workout_plan",
            "message": (
                "Нет сгенерированного плана тренировки. "
                "Сначала открой тренировку через «📋 По программе» или запроси тренировку, "
                "а потом можно будет заменить упражнение."
            ),
        }

    # Enrich exercises from DB with Russian names (for matching user's Russian input)
    exercises = _enrich_exercises_with_ru(exercises)

    # Fuzzy-find: substring match on English name or Russian name in both directions
    old_key = _normalize_key(old_exercise_name)
    match_idx = next(
        (
            i for i, ex in enumerate(exercises)
            if old_key in _normalize_key(ex.get("name", ""))
            or _normalize_key(ex.get("name", "")) in old_key
            or old_key in _normalize_key(ex.get("name_ru", ""))
            or _normalize_key(ex.get("name_ru", "")) in old_key
        ),
        None,
    )
    if match_idx is None:
        names = ", ".join(ex.get("name", "") for ex in exercises)
        return {
            "error": "exercise_not_found",
            "message": (
                f"Упражнение «{old_exercise_name}» не найдено в текущем плане тренировки. "
                f"В плане есть: {names}. "
                f"Уточни название или попроси заменить одно из перечисленных."
            ),
        }

    original = exercises[match_idx]

    if new_exercise_name:
        # User specified a replacement directly
        from agent.tools.exercise_db import get_ru_name
        replacement_ex = {
            "name": new_exercise_name,
            "name_ru": get_ru_name(new_exercise_name),
            "sets": original.get("sets", 3),
            "reps": original.get("reps", "10"),
            "weight_kg": original.get("weight_kg"),
            "rest_seconds": original.get("rest_seconds", 90),
        }
    else:
        # Auto-select from exercise DB: find muscle group of original exercise.
        # Use first 2 words of the name for matching (handles long descriptive names)
        orig_words = _normalize_key(original.get("name", "")).split()
        short_key = " ".join(orig_words[:2]) if len(orig_words) >= 2 else " ".join(orig_words)
        db_match = next(
            (
                ex for ex in EXERCISE_DB
                if short_key in _normalize_key(ex.name)
                or _normalize_key(ex.name) in _normalize_key(original.get("name", ""))
            ),
            None,
        )
        if db_match:
            muscle_group = db_match.muscle_group
        else:
            # Fall back to workout plan's focus field (set by get_next_session_plan)
            muscle_group = plan.get("focus") or "chest"
            logger.warning(
                "replace_workout_exercise: '%s' not in EXERCISE_DB, using muscle_group='%s'",
                original.get("name"), muscle_group,
            )

        # Load user injuries (equipment is on training_cycles, not users)
        profile = await fetchrow(
            "SELECT injuries FROM users WHERE telegram_user_id = $1", telegram_user_id
        ) or {}
        injuries: list[str] = profile.get("injuries") or []

        # Get equipment preference from the active cycle if available
        eq_filter: list[str] | None = None
        try:
            cycle_row = await fetchrow(
                "SELECT equipment FROM training_cycles "
                "WHERE user_id = $1 AND status = 'active' LIMIT 1",
                user_id,
            )
            if cycle_row and cycle_row.get("equipment"):
                eq_filter = [cycle_row["equipment"]]
        except Exception:
            logger.warning(
                "replace_workout_exercise: failed to fetch active cycle equipment for user %s",
                telegram_user_id, exc_info=True,
            )

        current_names = {_normalize_key(ex.get("name", "")) for ex in exercises}
        candidates = [
            ex for ex in get_safe_exercises(muscle_group, injuries, equipment=eq_filter, max_count=20)
            if _normalize_key(ex.name) not in current_names
            and _normalize_key(ex.name) != _normalize_key(original.get("name", ""))
        ]
        if not candidates:
            return {"error": f"Нет доступных замен для «{original['name']}» с учётом оборудования и противопоказаний"}

        chosen = candidates[0]
        from agent.tools.exercise_db import get_ru_name
        replacement_ex = {
            "name": chosen.name,
            "name_ru": get_ru_name(chosen.name),
            "sets": original.get("sets", 3),
            "reps": original.get("reps", "10"),
            "weight_kg": original.get("weight_kg"),
            "rest_seconds": original.get("rest_seconds", 90),
        }

    # Update plan
    updated_exercises = list(exercises)
    updated_exercises[match_idx] = replacement_ex
    updated_plan = {**plan, "exercises": updated_exercises}

    await execute(
        "UPDATE workouts SET plan = $1 WHERE id = $2",
        updated_plan, row["id"],
    )

    return {
        "replaced": original.get("name"),
        "with": replacement_ex["name"],
        "workout_id": row["id"],
        "updated_exercises": [ex.get("name") for ex in updated_exercises],
    }
