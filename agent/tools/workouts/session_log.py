"""Запись выполненной тренировки и история тренировок."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import execute, fetch, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import (
    _INCREMENT_COMPOUND,
    _INCREMENT_ISOLATION,
    _NO_WEIGHT_EQUIPMENT,
    _advance_cycle_position,
    _get_active_cycle_data,
    _normalize_key,
    _parse_reps,
)

logger = logging.getLogger(__name__)


@tool
async def log_workout(
    telegram_user_id: int,
    notes: str,
    workout_id: Optional[str] = None,
    performance: Optional[list[dict]] = None,
    done_as_planned: bool = False,
    cycle_id: Optional[str] = None,
    advance_cycle: bool = True,
) -> dict:
    """Записать выполненную тренировку.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        notes: Описание тренировки.
        workout_id: ID плана тренировки (если был).
        performance: Фактически выполненные упражнения.
            [{"name": "Bench Press", "sets_done": 3, "reps_done": 12, "weight_kg": 80}]
            Если None + done_as_planned=True + workout_id есть → скопировать из плана.
            Если None + workout_id нет → записать только факт тренировки.
        done_as_planned: True если пользователь сказал "всё по плану" — прогрессия не запускается.
        cycle_id: ID активного тренировочного цикла (если тренировка была частью цикла).
        advance_cycle: True чтобы автоматически продвинуть позицию в цикле (по умолчанию True).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"status": "error", "message": "Пользователь не найден."}

    # Fallback: done_as_planned + workout_id → copy reps lower bound from plan
    if performance is None and done_as_planned and workout_id:
        plan_row = await fetchrow(
            "SELECT plan FROM workouts WHERE id = $1", workout_id
        )
        plan_data = (plan_row or {}).get("plan") or {}
        plan_exercises = plan_data.get("exercises", [])
        if plan_exercises:
            performance = []
            for ex in plan_exercises:
                lo, _ = _parse_reps(ex.get("reps", "8"))
                performance.append({
                    "name": ex.get("name", ""),
                    "sets_done": ex.get("sets", 3),
                    "reps_done": lo,
                    "weight_kg": ex.get("weight_kg"),
                })

    # Add canonical key to each performance entry
    if performance:
        performance = [
            {**ex, "key": _normalize_key(ex.get("name", ""))}
            for ex in performance
        ]

    # Separate working sets from warmup/drop sets for PR, progression, volume
    working_performance = [
        ex for ex in (performance or []) if not ex.get("is_warmup")
    ]

    # Load user bodyweight for bodyweight exercise 1RM calculations
    profile_row = await fetchrow(
        "SELECT weight_kg FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    user_bodyweight: float | None = (profile_row or {}).get("weight_kg")

    # Load EXERCISE_DB for bodyweight detection
    from agent.tools.exercise_db import EXERCISE_DB
    ex_db_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Enrich performance with effective_weight (for bodyweight exercises)
    for ex in working_performance:
        key = ex.get("key", "")
        db_ex = ex_db_map.get(key)
        if db_ex and db_ex.uses_bodyweight and ex.get("weight_kg") is None and user_bodyweight:
            ex["effective_weight"] = user_bodyweight + (ex.get("added_kg") or 0)
        elif ex.get("weight_kg") is not None:
            ex["effective_weight"] = ex.get("weight_kg")

    # Query previous log BEFORE insert (for suggest_details)
    prev_log = await fetchrow(
        "SELECT done_as_planned FROM workout_logs WHERE user_id = $1 "
        "ORDER BY completed_at DESC LIMIT 1",
        user_id,
    )
    prev_was_as_planned = bool(prev_log and prev_log.get("done_as_planned"))
    has_weighted_exercises = bool(working_performance and any(ex.get("effective_weight") is not None for ex in working_performance))
    suggest_details = done_as_planned and prev_was_as_planned and has_weighted_exercises

    # PR detection: load history once, filter in Python (warmups excluded)
    pr_notes: list[str] = []
    if working_performance:
        history_rows = await fetch(
            "SELECT performance FROM workout_logs WHERE user_id = $1 "
            "ORDER BY completed_at DESC LIMIT 50",
            user_id,
        )
        all_past = [
            ex
            for log in history_rows
            for ex in (log.get("performance") or [])
            if not ex.get("is_warmup")
        ]

        # Enrich historical performance with effective_weight
        for h in all_past:
            key = h.get("key") or _normalize_key(h.get("name", ""))
            db_ex = ex_db_map.get(key)
            if db_ex and db_ex.uses_bodyweight and h.get("weight_kg") is None and user_bodyweight:
                h["effective_weight"] = user_bodyweight + (h.get("added_kg") or 0)
            elif h.get("weight_kg") is not None:
                h["effective_weight"] = h.get("weight_kg")

        for ex in working_performance:
            key = ex.get("key", "")
            same_ex = [h for h in all_past if h.get("key") == key]
            past_weights = [h.get("effective_weight") for h in same_ex if h.get("effective_weight") is not None]
            ex_weight = ex.get("effective_weight")
            ex_reps = ex.get("reps_done")
            ex_name = ex.get("name", "")

            if ex_weight is not None and (not past_weights or ex_weight > max(past_weights)):
                pr_notes.append(f"🏆 Рекорд по весу: {ex_name} — {ex_weight:.1f}кг!")
            elif ex_weight is not None and past_weights:
                same_weight = [h for h in same_ex if abs((h.get("effective_weight") or 0) - ex_weight) < 0.1]
                past_reps = [h["reps_done"] for h in same_weight if h.get("reps_done") is not None]
                if past_reps and ex_reps is not None and ex_reps > max(past_reps):
                    pr_notes.append(f"🏆 Рекорд по повт.: {ex_name} — {ex_weight:.1f}кг × {ex_reps}!")

    # Build next_session recommendations (only if workout_id and not done_as_planned)
    next_session: list[dict] = []
    if workout_id and not done_as_planned and working_performance:
        plan_row = await fetchrow(
            "SELECT plan FROM workouts WHERE id = $1", workout_id
        )
        plan_data = (plan_row or {}).get("plan") or {}
        plan_exercises = plan_data.get("exercises", [])
        perf_by_key = {ex.get("key", ""): ex for ex in working_performance}

        for planned_ex in plan_exercises:
            key = _normalize_key(planned_ex.get("name", ""))
            actual = perf_by_key.get(key)
            if not actual:
                continue
            lo, hi = _parse_reps(planned_ex.get("reps", "8"))
            reps_done = actual.get("reps_done") or 0
            weight = actual.get("weight_kg")

            db_ex = ex_db_map.get(key)
            is_compound = db_ex.is_compound if db_ex else False
            equipment_set = db_ex.equipment if db_ex else frozenset()

            ex_name = planned_ex.get("name", "")
            if equipment_set <= _NO_WEIGHT_EQUIPMENT or weight is None:
                # Bodyweight: suggest more reps
                if reps_done >= hi:
                    note = "↑ +2 повт."
                    next_reps = f"{lo + 2}-{hi + 2}"
                    reasoning = (
                        f"Ты сделал {reps_done} повт. (диапазон: {lo}–{hi}) → "
                        f"достиг верхней границы → +2 повт. на следующей"
                    )
                else:
                    note = f"→ цель {reps_done + 1}+ повт."
                    next_reps = f"{lo}-{hi}"
                    reasoning = (
                        f"Ты сделал {reps_done} повт. (диапазон: {lo}–{hi}) → "
                        f"в рабочем диапазоне → тот же вес, цель +1 повт."
                    )
                next_session.append({
                    "name": ex_name,
                    "weight_kg": None,
                    "reps": next_reps,
                    "note": note,
                    "reasoning": reasoning,
                })
            else:
                increment = _INCREMENT_COMPOUND if is_compound else _INCREMENT_ISOLATION
                ex_type = "компаунд" if is_compound else "изоляция"
                if reps_done >= hi:
                    next_weight = weight + increment
                    next_reps = f"{lo}-{hi}"
                    note = f"↑ +{increment}кг"
                    reasoning = (
                        f"Ты сделал {weight}кг × {reps_done} (диапазон: {lo}–{hi}) → "
                        f"достиг верхней границы → {ex_type} +{increment}кг = {next_weight}кг"
                    )
                elif reps_done >= lo:
                    next_weight = weight
                    next_reps = f"{lo}-{hi}"
                    note = f"→ тот же вес, цель {reps_done + 1}+ повт."
                    reasoning = (
                        f"Ты сделал {weight}кг × {reps_done} (диапазон: {lo}–{hi}) → "
                        f"в рабочем диапазоне → тот же вес, цель {reps_done + 1}+ повт."
                    )
                else:
                    next_weight = weight
                    next_reps = f"{lo}-{hi}"
                    note = f"⚠️ тот же вес, добери до {lo} повт."
                    reasoning = (
                        f"Ты сделал {weight}кг × {reps_done} (диапазон: {lo}–{hi}) → "
                        f"не добрал до нижней границы → тот же вес"
                    )
                next_session.append({
                    "name": ex_name,
                    "weight_kg": next_weight,
                    "reps": next_reps,
                    "note": note,
                    "reasoning": reasoning,
                })

    record: dict = {
        "user_id": user_id,
        "notes": notes,
        "completed_at": datetime.now(timezone.utc),
        "done_as_planned": done_as_planned,
    }
    if workout_id:
        record["workout_id"] = workout_id
    if performance:
        record["performance"] = performance

    # Resolve active cycle if not provided explicitly
    active_cycle_id = cycle_id
    cycle_row: dict | None = None  # always initialize to avoid NameError
    if not active_cycle_id:
        cycle_row = await _get_active_cycle_data(user_id)
        if cycle_row:
            active_cycle_id = cycle_row["id"]

    if active_cycle_id:
        if cycle_id:
            # cycle_id was provided directly — load its row
            cycle_row = await fetchrow(
                "SELECT current_week, current_session_index FROM training_cycles WHERE id = $1",
                active_cycle_id,
            )
        if cycle_row:
            record["cycle_id"] = active_cycle_id
            record["cycle_week"] = cycle_row.get("current_week")
            record["cycle_session_index"] = cycle_row.get("current_session_index")

    # Upsert logic: if a log for the same workout_id was created in the last 8 hours,
    # UPDATE it (user clarified details) instead of INSERT a duplicate.
    existing_log_id: str | None = None
    if workout_id:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=8)
        existing_row = await fetchrow(
            "SELECT id FROM workout_logs WHERE user_id = $1 AND workout_id = $2 "
            "AND completed_at >= $3 ORDER BY completed_at DESC LIMIT 1",
            user_id, workout_id, cutoff,
        )
        if existing_row:
            existing_log_id = existing_row["id"]

    cycle_advancement = None
    if existing_log_id:
        # Update existing record — user is providing real details for the same session
        columns = list(record.keys())
        set_clause = ", ".join(f"{col} = ${i + 1}" for i, col in enumerate(columns))
        args = [record[col] for col in columns]
        args.append(existing_log_id)
        await execute(
            f"UPDATE workout_logs SET {set_clause} WHERE id = ${len(args)}",
            *args,
        )
        # Cycle was already advanced on the first insert — skip re-advancing
    else:
        columns = list(record.keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        args = [record[col] for col in columns]
        await execute(
            f"INSERT INTO workout_logs ({col_list}) VALUES ({placeholders})",
            *args,
        )
        # Advance cycle position after first insert
        if active_cycle_id and advance_cycle:
            cycle_advancement = await _advance_cycle_position(user_id, active_cycle_id)
            if cycle_advancement.get("reason") == "concurrent_update":
                # Retry once
                cycle_advancement = await _advance_cycle_position(user_id, active_cycle_id)

    return {
        "status": "logged",
        "message": "+1 тренировка в копилку 💪",
        "next_session": next_session,
        "pr_notes": pr_notes,
        "suggest_details": suggest_details,
        "cycle_advancement": cycle_advancement,
    }


@tool
async def get_workout_history(telegram_user_id: int, limit: int = 5) -> list[dict]:
    """Получить историю тренировок пользователя (последние N записей)."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return []

    rows = await fetch(
        "SELECT wl.*, w.title AS workout_title FROM workout_logs wl "
        "LEFT JOIN workouts w ON wl.workout_id = w.id "
        "WHERE wl.user_id = $1 "
        "ORDER BY wl.completed_at DESC LIMIT $2",
        user_id, limit,
    )
    for row in rows:
        row["workouts"] = {"title": row.pop("workout_title", None)}
    return rows
