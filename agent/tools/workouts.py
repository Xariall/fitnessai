import logging
import re as _re
import unicodedata as _ud
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)

_INCREMENT_COMPOUND = 2.5
_INCREMENT_ISOLATION = 1.25
_NO_WEIGHT_EQUIPMENT = frozenset({"none"})


def _parse_reps(reps) -> tuple[int, int]:
    """Parse "8-10", "8 - 10", "8–10", "8", 10 → (lo, hi). Returns (0, 0) on failure."""
    s = str(reps).strip()
    m = _re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _re.search(r"(\d+)", s)
    if m:
        v = int(m.group(1))
        return v, v
    return 0, 0


def _normalize_key(name: str) -> str:
    """Canonical exercise key: 'Bench-Press', 'жим лёжа', 'BENCH PRESS' → unified key."""
    s = _ud.normalize("NFC", name.lower().strip())
    s = s.replace("ё", "е").replace("-", " ")
    s = _re.sub(r"\s+", " ", s)
    return s


def _calc_1rm(weight: float, reps: int) -> float:
    """Формула Эпли: оценка 1RM по рабочему весу и повторениям."""
    if reps <= 0 or weight <= 0:
        return 0.0
    if reps == 1:
        return weight
    return round(weight * (1 + reps / 30), 1)


def _ema(values: list[float], alpha: float = 0.4) -> list[float]:
    """Экспоненциальное скользящее среднее (EMA) для сглаживания ряда."""
    if not values:
        return []
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


_MUSCLE_KEYWORDS: dict[str, list[str]] = {
    "chest": ["грудь", "жим", "chest", "отжимания", "грудных"],
    "back": ["спина", "тяга", "подтягивания", "back", "спины"],
    "legs": ["ноги", "приседания", "выпады", "ягодицы", "legs", "квадрицепс", "бедра"],
    "shoulders": ["плечи", "дельты", "жим сидя", "shoulders", "плечей"],
    "arms": ["руки", "бицепс", "трицепс", "arms"],
    "biceps": ["бицепс", "biceps", "curl"],
    "triceps": ["трицепс", "triceps"],
    "core": ["пресс", "кор", "core", "планка", "скручивания"],
    "cardio": ["кардио", "бег", "cardio", "велосипед", "скакалка"],
    "strength": ["сила", "strength", "силовая"],
    "flexibility": ["растяжка", "гибкость", "flexibility", "мобилити"],
}


async def _get_recent_plan(user_id: str, focus: str, days: int = 7) -> dict | None:
    """Look up last workout with matching focus within the given day window."""
    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        await client.table("workouts")
        .select("id, title, plan, created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    rows = result.data or []
    focus_lower = focus.lower()
    keywords = _MUSCLE_KEYWORDS.get(focus_lower, [focus_lower])
    for row in rows:
        title_lower = (row.get("title") or "").lower()
        if any(kw in title_lower for kw in keywords):
            plan = row.get("plan") or {}
            exercises = plan.get("exercises", [])
            exercises_summary = ", ".join(
                f"{ex.get('name', '')} {ex.get('sets', '')}×{ex.get('reps', '')}"
                for ex in exercises[:6]
            )
            log_result = (
                await client.table("workout_logs")
                .select("performance, done_as_planned")
                .eq("user_id", user_id)
                .eq("workout_id", row["id"])
                .order("completed_at", desc=True)
                .limit(1)
                .execute()
            )
            last_log = (log_result.data or [None])[0]
            return {
                "title": row["title"],
                "exercises_summary": exercises_summary,
                "plan_exercises": exercises,
                "last_performance": (last_log or {}).get("performance") or [],
                "last_done_as_planned": (last_log or {}).get("done_as_planned", False),
            }
    return None


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

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
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
            saved = (
                await client.table("workouts")
                .insert({"user_id": user_id, "title": plan.get("title", focus), "plan": plan})
                .execute()
            )
            plan["id"] = saved.data[0]["id"] if saved.data else None
        except Exception:
            logger.exception("Failed to save workout to DB for user %s", telegram_user_id)

    return plan


@tool
async def update_user_injuries(telegram_user_id: int, injuries: list[str]) -> str:
    """Обновить список травм/противопоказаний пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        injuries: Список тегов травм (knee_injury/lower_back/shoulder_injury/elbow/wrist/hip/neck).
                  Передай [] чтобы очистить список.
    """
    from agent.tools.exercise_db import VALID_INJURY_TAGS, injury_label

    unknown = [i for i in injuries if i not in VALID_INJURY_TAGS]
    if unknown:
        valid = ", ".join(sorted(VALID_INJURY_TAGS))
        logger.warning("Unknown injury tags: %s. Valid: %s", unknown, valid)

    client = await get_client()
    await (
        client.table("users")
        .update({"injuries": injuries})
        .eq("telegram_user_id", telegram_user_id)
        .execute()
    )

    if not injuries:
        return "Список травм очищен. Буду предлагать все упражнения без ограничений."

    listed = ", ".join(injury_label(i) for i in injuries)
    return (
        f"Записал противопоказания: {listed}. "
        f"Буду автоматически исключать опасные упражнения при составлении тренировок."
    )


@tool
async def get_recovery_overview(telegram_user_id: int) -> dict:
    """Получить статус восстановления по всем основным группам мышц за один вызов.

    Используй этот инструмент когда нужен общий обзор восстановления — вместо
    того чтобы вызывать check_recovery_status отдельно для каждой группы.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    from agent.tools.exercise_db import get_safe_exercises

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"groups": {}, "recommended": [], "injuries": [], "error": "Пользователь не найден."}

    client = await get_client()

    profile_result = (
        await client.table("users")
        .select("injuries")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    injuries: list[str] = (profile_result.data or {}).get("injuries") or []

    since_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    result = (
        await client.table("workout_logs")
        .select("completed_at, notes, workouts(title, plan)")
        .eq("user_id", user_id)
        .gte("completed_at", since_48h)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = result.data or []

    # Pre-compute combined text once per log entry (reused across all 7 group checks)
    log_entries: list[tuple[str, str]] = []
    for log in logs:
        notes_lower = (log.get("notes") or "").lower()
        workout = log.get("workouts") or {}
        title_lower = (workout.get("title") or "").lower()
        plan = workout.get("plan") or {}
        exercises_text = " ".join(
            ex.get("name", "").lower() for ex in plan.get("exercises", [])
        )
        log_entries.append((f"{notes_lower} {title_lower} {exercises_text}", log["completed_at"]))

    _MAIN_GROUPS = ["chest", "back", "legs", "shoulders", "arms", "core", "cardio"]
    groups: dict = {}
    recommended: list[str] = []

    for group in _MAIN_GROUPS:
        contraindicated = not get_safe_exercises(group, injuries, max_count=1) and bool(injuries)

        status = "contraindicated" if contraindicated else "ready"
        hours_since_last: int | None = None
        keywords = _MUSCLE_KEYWORDS.get(group, [group])

        if not contraindicated:
            for combined, completed_at in log_entries:
                if any(kw in combined for kw in keywords):
                    ts = completed_at.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts)
                    hours_since_last = round(
                        (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
                    )
                    status = "needs_rest"
                    break

        groups[group] = {
            "status": status,
            "hours_since_last": hours_since_last,
            "contraindicated": contraindicated,
        }
        if status == "ready":
            recommended.append(group)

    return {"groups": groups, "recommended": recommended, "injuries": injuries}


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

    client = await get_client()

    # Fallback: done_as_planned + workout_id → copy reps lower bound from plan
    if performance is None and done_as_planned and workout_id:
        plan_result = (
            await client.table("workouts")
            .select("plan")
            .eq("id", workout_id)
            .single()
            .execute()
        )
        plan_data = (plan_result.data or {}).get("plan") or {}
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

    # Query previous log BEFORE insert (for suggest_details)
    prev_logs = (
        await client.table("workout_logs")
        .select("done_as_planned")
        .eq("user_id", user_id)
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    prev_was_as_planned = bool(prev_logs and prev_logs[0].get("done_as_planned"))
    has_weighted_exercises = bool(performance and any(ex.get("weight_kg") is not None for ex in performance))
    suggest_details = done_as_planned and prev_was_as_planned and has_weighted_exercises

    # PR detection: load history once, filter in Python
    pr_notes: list[str] = []
    if performance:
        history_result = (
            await client.table("workout_logs")
            .select("performance")
            .eq("user_id", user_id)
            .order("completed_at", desc=True)
            .limit(50)
            .execute()
        )
        all_past = [
            ex
            for log in (history_result.data or [])
            for ex in (log.get("performance") or [])
        ]
        for ex in performance:
            key = ex.get("key", "")
            same_ex = [h for h in all_past if h.get("key") == key]
            past_weights = [h["weight_kg"] for h in same_ex if h.get("weight_kg") is not None]
            ex_weight = ex.get("weight_kg")
            ex_reps = ex.get("reps_done")
            ex_name = ex.get("name", "")
            if ex_weight is not None and (not past_weights or ex_weight > max(past_weights)):
                pr_notes.append(f"🏆 Рекорд по весу: {ex_name} — {ex_weight}кг!")
            elif ex_weight is not None and past_weights:
                same_weight = [h for h in same_ex if h.get("weight_kg") == ex_weight]
                past_reps = [h["reps_done"] for h in same_weight if h.get("reps_done") is not None]
                if past_reps and ex_reps is not None and ex_reps > max(past_reps):
                    pr_notes.append(f"🏆 Рекорд по повт.: {ex_name} — {ex_weight}кг × {ex_reps}!")

    # Build next_session recommendations (only if workout_id and not done_as_planned)
    next_session: list[dict] = []
    if workout_id and not done_as_planned and performance:
        plan_result = (
            await client.table("workouts")
            .select("plan")
            .eq("id", workout_id)
            .single()
            .execute()
        )
        plan_data = (plan_result.data or {}).get("plan") or {}
        plan_exercises = plan_data.get("exercises", [])
        perf_by_key = {ex.get("key", ""): ex for ex in performance}

        from agent.tools.exercise_db import EXERCISE_DB
        ex_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

        for planned_ex in plan_exercises:
            key = _normalize_key(planned_ex.get("name", ""))
            actual = perf_by_key.get(key)
            if not actual:
                continue
            lo, hi = _parse_reps(planned_ex.get("reps", "8"))
            reps_done = actual.get("reps_done") or 0
            weight = actual.get("weight_kg")

            db_ex = ex_map.get(key)
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
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "done_as_planned": done_as_planned,
    }
    if workout_id:
        record["workout_id"] = workout_id
    if performance:
        record["performance"] = performance

    # Resolve active cycle if not provided explicitly
    active_cycle_id = cycle_id
    if not active_cycle_id:
        cycle_row = await _get_active_cycle_data(user_id)
        if cycle_row:
            active_cycle_id = cycle_row["id"]

    if active_cycle_id:
        cycle_row = cycle_row if not cycle_id else (
            await (await get_client()).table("training_cycles")
            .select("current_week,current_session_index")
            .eq("id", active_cycle_id).single().execute()
        ).data
        if cycle_row:
            record["cycle_id"] = active_cycle_id
            record["cycle_week"] = cycle_row.get("current_week")
            record["cycle_session_index"] = cycle_row.get("current_session_index")

    await client.table("workout_logs").insert(record).execute()

    # Advance cycle position after insert
    cycle_advancement = None
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

    client = await get_client()
    result = (
        await client.table("workout_logs")
        .select("*, workouts(title)")
        .eq("user_id", user_id)
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@tool
async def check_recovery_status(
    telegram_user_id: int,
    muscle_group: str,
) -> dict:
    """Check if a muscle group has recovered and is ready to train (48h rule).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        muscle_group: Группа мышц (chest/back/legs/shoulders/arms/core/cardio).
    """
    from agent.tools.exercise_db import get_safe_exercises, injury_label

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"can_train": True, "status": "ready", "message": "Нет данных о тренировках — начинай!"}

    client = await get_client()

    # Check for contraindications first
    profile_result = (
        await client.table("users")
        .select("injuries")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    injuries: list[str] = (profile_result.data or {}).get("injuries") or []
    safe = get_safe_exercises(muscle_group, injuries, max_count=1)
    if not safe and injuries:
        listed = ", ".join(injury_label(i) for i in injuries)
        return {
            "can_train": False,
            "status": "contraindicated",
            "message": (
                f"Из-за травм ({listed}) для группы «{muscle_group}» нет безопасных упражнений. "
                f"Рекомендую другую группу мышц или растяжку."
            ),
        }

    # 48h recovery check
    since_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    result = (
        await client.table("workout_logs")
        .select("completed_at, notes, workouts(title, plan)")
        .eq("user_id", user_id)
        .gte("completed_at", since_48h)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = result.data or []

    if not logs:
        return {
            "can_train": True,
            "status": "ready",
            "message": "Последние 48 часов без тренировок. Готов к работе 💪",
            "last_trained": None,
        }

    keywords = _MUSCLE_KEYWORDS.get(muscle_group.lower(), [muscle_group.lower()])
    for log in logs:
        notes_lower = (log.get("notes") or "").lower()
        workout = log.get("workouts") or {}
        title_lower = (workout.get("title") or "").lower()
        plan = workout.get("plan") or {}
        exercises_text = " ".join(
            ex.get("name", "").lower() for ex in plan.get("exercises", [])
        )
        combined = f"{notes_lower} {title_lower} {exercises_text}"

        if any(kw in combined for kw in keywords):
            completed_at = log["completed_at"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(completed_at)
            hours_ago = round(
                (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
            )
            return {
                "can_train": False,
                "status": "needs_rest",
                "message": (
                    f"Группа «{muscle_group}» тренировалась {hours_ago}ч назад. "
                    "Рекомендуется отдых или другая группа мышц."
                ),
                "hours_since_last": hours_ago,
                "last_trained": log["completed_at"],
            }

    return {
        "can_train": True,
        "status": "ready",
        "message": f"Группа «{muscle_group}» готова — за последние 48 часов не тренировалась.",
        "last_trained": None,
    }


async def _advance_cycle_position(user_id: str, cycle_id: str) -> dict:
    """Advance current_session_index; roll to next week when sessions exhausted.

    Uses optimistic locking to guard against concurrent writes — if the row
    changed between read and update, returns reason="concurrent_update".
    """
    client = await get_client()

    row = (
        await client.table("training_cycles")
        .select("*")
        .eq("id", cycle_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    ).data

    if not row:
        return {"advanced": False, "reason": "cycle_not_found"}
    if row["status"] != "active":
        return {"advanced": False, "reason": "not_active", "status": row["status"]}

    cur_sess  = row["current_session_index"]
    cur_week  = row["current_week"]
    sess_per  = row["sessions_per_week"]
    total_wks = row["total_weeks"]
    done      = row["total_sessions_done"] + 1

    next_sess = cur_sess + 1
    next_week = cur_week
    if next_sess >= sess_per:
        next_sess = 0
        next_week += 1

    is_complete = next_week > total_wks
    new_status  = "completed" if is_complete else "active"

    update: dict = {
        "current_session_index": next_sess,
        "current_week":          min(next_week, total_wks),
        "total_sessions_done":   done,
        "status":                new_status,
    }
    if is_complete and not row.get("completed_at"):
        from datetime import timezone
        update["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Optimistic locking: only update if position AND status haven't changed
    result = (
        await client.table("training_cycles")
        .update(update)
        .eq("id", cycle_id)
        .eq("current_session_index", cur_sess)
        .eq("current_week", cur_week)
        .eq("status", "active")
        .execute()
    )

    if not result.data:
        return {"advanced": False, "reason": "concurrent_update"}

    return {
        "advanced": True,
        "new_week": next_week,
        "new_session_index": next_sess,
        "is_complete": is_complete,
        "total_sessions_done": done,
    }


async def _get_active_cycle_data(user_id: str) -> dict | None:
    """Return the active training_cycles row for a user, or None."""
    client = await get_client()
    rows = (
        await client.table("training_cycles")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data
    return rows[0] if rows else None


@tool
async def create_training_cycle(
    telegram_user_id: int,
    goal: str,
    weeks: int = 6,
    sessions_per_week: int = 3,
    training_type: Optional[str] = None,
    equipment: Optional[str] = None,
    force_replace: bool = False,
) -> dict:
    """Создать многонедельный тренировочный цикл и сделать его активным.

    Перед созданием проверяет наличие активного цикла. Если он есть и force_replace=False —
    возвращает status='active_cycle_exists' с предупреждением. Агент должен показать
    предупреждение пользователю и запросить явное подтверждение, после чего вызвать
    эту функцию с force_replace=True.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        goal: Цель (gain_muscle / lose_weight / strength / endurance).
        weeks: Количество недель (4–8).
        sessions_per_week: Тренировок в неделю (2–5).
        training_type: Стиль тренинга (strength / hypertrophy / functional / mixed).
        equipment: Оборудование (gym / home_dumbbells / bodyweight).
        force_replace: True = пользователь явно подтвердил замену активного цикла.
    """
    import json
    import re

    from pydantic import ValidationError

    from db.models import TrainingCycleSchedule
    from llm.provider import get_llm

    weeks = max(4, min(weeks, 8))
    sessions_per_week = max(2, min(sessions_per_week, 5))

    client = await get_client()

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # Check for existing active cycle before doing anything expensive
    existing = (
        await client.table("training_cycles")
        .select("id,title,current_week,total_weeks")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    ).data
    if existing and not force_replace:
        c = existing[0]
        return {
            "status": "active_cycle_exists",
            "title": c["title"],
            "current_week": c["current_week"],
            "total_weeks": c["total_weeks"],
            "message": (
                f"У тебя активна программа «{c['title']}», "
                f"неделя {c['current_week']} из {c['total_weeks']}. "
                "Создать новую и завершить текущую? Напиши «да» для подтверждения."
            ),
        }

    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    injuries: list[str] = profile.get("injuries") or []

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"ПРОТИВОПОКАЗАНИЯ: {listed}. Исключи фокусы с нагрузкой на эти зоны.\n"

    training_type_note = f"Тип тренинга: {training_type}.\n" if training_type else ""
    equipment_note = f"Оборудование: {equipment}.\n" if equipment else ""

    from agent.prompts.system import CYCLE_PHASE_RULES

    llm = get_llm()
    prompt = (
        f"{CYCLE_PHASE_RULES}\n\n"
        f"---\n"
        f"Составь расписание тренировочного цикла на {weeks} недель, {sessions_per_week} тренировки/нед.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
        f"{training_type_note}{equipment_note}{injuries_note}"
        f"Верни ТОЛЬКО JSON в этом формате (без пояснений):\n"
        f'{{"title": "Силовой цикл {weeks} недель", '
        f'"weeks": ['
        f'{{"week_number": 1, "theme": "Накопление объёма", "phase": "accumulation", '
        f'"sessions": ['
        f'{{"session_index": 0, "focus": "chest", "label": "Грудь / Трицепс"}}, '
        f'{{"session_index": 1, "focus": "legs", "label": "Ноги"}}, '
        f'{{"session_index": 2, "focus": "back", "label": "Спина / Бицепс"}}'
        f']}}'
        f']}}'
        f'\n\nВажно: у каждой недели должно быть ровно {sessions_per_week} сессий. '
        f'Все {weeks} недель. Используй focus: chest/back/legs/shoulders/arms/core.'
    )

    # LLM call with schedule validation and one retry
    parsed: dict = {}
    for attempt in range(2):
        try:
            response = await llm.ainvoke(prompt)
            raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
        except Exception:
            logger.exception("LLM failed in create_training_cycle for user %s", telegram_user_id)
            return {"error": "Не удалось создать цикл — ошибка LLM"}

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            parsed = json.loads(match.group()) if match else {}
        except json.JSONDecodeError:
            logger.warning("JSON parse failed in create_training_cycle attempt %d, raw=%r", attempt, raw[:200])
            if attempt == 1:
                return {"error": "Не удалось разобрать ответ модели"}
            continue

        if not parsed or "weeks" not in parsed:
            if attempt == 1:
                return {"error": "Не удалось разобрать ответ модели"}
            continue

        # Validate schedule structure via Pydantic
        try:
            TrainingCycleSchedule.model_validate({"weeks": parsed["weeks"]})
            break  # Validation passed
        except ValidationError as e:
            logger.warning("schedule validation failed attempt %d: %s", attempt, e)
            if attempt == 1:
                return {"error": f"Не удалось сгенерировать корректное расписание: {e}"}
            # Retry with explicit reminder
            prompt += f"\n\nПредыдущий ответ не прошёл валидацию: {e}\nПопробуй ещё раз строго по формату."

    # Deactivate existing active cycle (force_replace=True confirmed by user)
    try:
        await client.table("training_cycles").update({"status": "completed"}).eq(
            "user_id", user_id
        ).eq("status", "active").execute()
    except Exception:
        logger.warning("Failed to deactivate old cycle for user %s", telegram_user_id)

    title = parsed.get("title") or f"{goal.replace('_', ' ').title()} цикл {weeks} нед."
    schedule = {"weeks": parsed["weeks"]}

    try:
        insert_data: dict = {
            "user_id": user_id,
            "title": title,
            "goal": goal,
            "total_weeks": weeks,
            "sessions_per_week": sessions_per_week,
            "schedule": schedule,
        }
        if training_type:
            insert_data["training_type"] = training_type
        if equipment:
            insert_data["equipment"] = equipment

        saved = (
            await client.table("training_cycles")
            .insert(insert_data)
            .execute()
        )
        cycle_id = saved.data[0]["id"] if saved.data else None
    except Exception:
        logger.exception("Failed to save training cycle for user %s", telegram_user_id)
        return {"error": "Не удалось сохранить цикл в БД"}

    # Build next_session info for the response
    try:
        first_session = parsed["weeks"][0]["sessions"][0]
        next_session = {
            "focus": first_session.get("focus"),
            "label": first_session.get("label"),
            "week": 1,
            "session_number": 1,
        }
    except (IndexError, KeyError):
        next_session = None

    return {
        "cycle_id": cycle_id,
        "title": title,
        "goal": goal,
        "total_weeks": weeks,
        "sessions_per_week": sessions_per_week,
        "training_type": training_type,
        "equipment": equipment,
        "week_1_theme": parsed["weeks"][0].get("theme") if parsed["weeks"] else "",
        "next_session": next_session,
        "schedule": schedule,
    }


@tool
async def get_exercise_history(
    telegram_user_id: int,
    exercise_name: str,
    limit: int = 10,
) -> list[dict]:
    """История результатов по конкретному упражнению (вес × повторения по датам).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        exercise_name: Название упражнения (например "Bench Press" или "жим лёжа").
        limit: Максимальное количество записей (по умолчанию 10).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return [{"error": "Пользователь не найден."}]

    client = await get_client()
    since_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    search_key = _normalize_key(exercise_name)

    logs_result = (
        await client.table("workout_logs")
        .select("completed_at, performance")
        .eq("user_id", user_id)
        .gte("completed_at", since_90d)
        .order("completed_at", desc=True)
        .limit(limit * 5)
        .execute()
    )
    logs = logs_result.data or []

    # Exact key match first
    history: list[dict] = []
    for log in logs:
        for ex in (log.get("performance") or []):
            if ex.get("key") == search_key:
                history.append({
                    "date": log["completed_at"][:10],
                    "name": ex.get("name"),
                    "weight_kg": ex.get("weight_kg"),
                    "reps_done": ex.get("reps_done"),
                    "sets_done": ex.get("sets_done"),
                })
                break
        if len(history) >= limit:
            break

    # Partial match fallback
    if not history:
        for log in logs:
            for ex in (log.get("performance") or []):
                if search_key in (ex.get("key") or ""):
                    history.append({
                        "date": log["completed_at"][:10],
                        "name": ex.get("name"),
                        "weight_kg": ex.get("weight_kg"),
                        "reps_done": ex.get("reps_done"),
                        "sets_done": ex.get("sets_done"),
                    })
                    break
            if len(history) >= limit:
                break
        names = {e["name"] for e in history if e.get("name")}
        if len(names) > 1:
            return [{"warning": f"Уточни название: найдено {', '.join(sorted(names))}."}]

    if not history:
        return [{"message": f"История по упражнению '{exercise_name}' не найдена за последние 90 дней."}]

    return list(reversed(history))


@tool
async def get_training_roadmap(telegram_user_id: int) -> dict:
    """Дорожная карта прогресса по всем упражнениям за последние 60 дней.

    Показывает историю весов и повторений, тренд прогрессии, и следующую цель для каждого упражнения.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"exercises": {}, "total_sessions": 0, "error": "Пользователь не найден."}

    client = await get_client()
    since_60d = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

    logs_result = (
        await client.table("workout_logs")
        .select("completed_at, performance")
        .eq("user_id", user_id)
        .gte("completed_at", since_60d)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = logs_result.data or []

    if not logs:
        return {
            "exercises": {},
            "total_sessions": 0,
            "message": "Пока нет записей тренировок. Начни первую — и roadmap заполнится!",
        }

    from agent.tools.exercise_db import EXERCISE_DB
    ex_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Load user profile for bodyweight 1RM estimation
    profile_result = (
        await client.table("users")
        .select("weight_kg")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    bodyweight_kg: float | None = (profile_result.data or {}).get("weight_kg")

    # Aggregate per exercise key in chronological order (logs are desc, so reversed)
    key_data: dict[str, list[dict]] = {}
    for log in reversed(logs):
        date = log["completed_at"][:10]
        for ex in (log.get("performance") or []):
            key = ex.get("key") or _normalize_key(ex.get("name", ""))
            if key not in key_data:
                key_data[key] = []
            key_data[key].append({
                "date": date,
                "name": ex.get("name"),
                "weight_kg": ex.get("weight_kg"),
                "reps_done": ex.get("reps_done"),
                "sets_done": ex.get("sets_done"),
                "rir": ex.get("rir"),
                "added_kg": ex.get("added_kg"),
            })

    exercises: dict = {}
    for key, history_points in key_data.items():
        if not history_points:
            continue

        display_name = history_points[-1].get("name") or key
        weights = [p["weight_kg"] for p in history_points if p.get("weight_kg") is not None]

        if len(weights) >= 2:
            delta = round(weights[-1] - weights[0], 2)
            if delta > 0:
                trend = f"↑ +{delta}кг"
            elif delta < 0:
                trend = f"↓ {delta}кг"
            else:
                trend = "→ без изменений"
        elif weights:
            trend = "данных пока мало"
        else:
            trend = "вес не фиксировался"

        next_target = None
        if weights:
            db_ex = ex_map.get(key)
            is_compound = db_ex.is_compound if db_ex else False
            increment = _INCREMENT_COMPOUND if is_compound else _INCREMENT_ISOLATION
            next_target = round(weights[-1] + increment, 2)

        # ── 1RM + analytics ─────────────────────────────────────────────
        one_rm_series: list[float] = []
        rir_values: list[float] = []

        for p in history_points:
            w = p.get("weight_kg")
            r = p.get("reps_done") or 0
            added = p.get("added_kg")
            rir = p.get("rir")

            if rir is not None:
                rir_values.append(float(rir))

            effective_w: float | None = None
            if w is not None and w > 0:
                effective_w = w
            elif added is not None and bodyweight_kg:
                effective_w = bodyweight_kg + added  # оценка

            if effective_w and r > 0:
                one_rm_series.append(_calc_1rm(effective_w, r))

        avg_rir: float | None = round(sum(rir_values) / len(rir_values), 1) if rir_values else None
        estimated_1rm: float | None = round(one_rm_series[-1], 1) if one_rm_series else None
        max_1rm: float | None = round(max(one_rm_series), 1) if one_rm_series else None

        # Plateau detection
        plateau_detected = False
        underload_detected = False
        sessions_since_progress = 0
        trend_score: float | None = None
        trend_label = "insufficient_data"

        if one_rm_series:
            max_idx = one_rm_series.index(max(one_rm_series))
            sessions_since_progress = len(one_rm_series) - 1 - max_idx

            weeks_since_progress = 0.0
            if sessions_since_progress > 0:
                try:
                    last_progress_dt = datetime.fromisoformat(
                        history_points[max_idx]["date"]
                    )
                    latest_dt = datetime.fromisoformat(history_points[-1]["date"])
                    weeks_since_progress = (latest_dt - last_progress_dt).days / 7
                except (ValueError, KeyError):
                    pass

            # Priority: underload first (avg_rir > 3 = not plateau, just too easy)
            if avg_rir is not None and avg_rir > 3:
                underload_detected = True
            else:
                plateau_detected = sessions_since_progress >= 5 or weeks_since_progress >= 3

        # Trend score (requires ≥3 points for EMA)
        if len(one_rm_series) >= 3:
            smoothed = _ema(one_rm_series)
            first_s, last_s = smoothed[0], smoothed[-1]
            delta_pct = ((last_s - first_s) / first_s * 100) if first_s else 0.0

            mid = len(history_points) // 2
            first_sets = sum((p.get("sets_done") or 1) for p in history_points[:mid])
            second_sets = sum((p.get("sets_done") or 1) for p in history_points[mid:])
            vol_delta_pct = ((second_sets - first_sets) / first_sets * 100) if first_sets else 0.0

            rir_modifier = 1.0
            if avg_rir is not None:
                rir_modifier = max(0.0, 1.0 - (avg_rir - 2) * 0.1)

            trend_score = round((delta_pct * 0.7 + vol_delta_pct * 0.3) * rir_modifier, 2)

        # trend_label (mutual exclusive, priority order)
        if underload_detected:
            trend_label = "underload"
        elif plateau_detected:
            trend_label = "plateau"
        elif trend_score is not None:
            if trend_score > 0:
                trend_label = "up"
            elif trend_score < 0:
                trend_label = "down"
            else:
                trend_label = "stable"
        elif len(one_rm_series) >= 2:
            delta_simple = one_rm_series[-1] - one_rm_series[-2]
            trend_label = "up" if delta_simple > 0 else ("down" if delta_simple < 0 else "stable")

        exercises[key] = {
            "display_name": display_name,
            "history": [
                {
                    "date": p["date"],
                    "weight_kg": p.get("weight_kg"),
                    "reps_done": p.get("reps_done"),
                    "rir": p.get("rir"),
                }
                for p in history_points
            ],
            "trend": trend,
            "next_target": next_target,
            "sessions_count": len(history_points),
            # 1RM analytics
            "estimated_1rm": estimated_1rm,
            "max_1rm": max_1rm,
            "avg_rir": avg_rir,
            # Progression state
            "plateau_detected": plateau_detected,
            "underload_detected": underload_detected,
            "sessions_since_progress": sessions_since_progress,
            # Trend
            "trend_score": trend_score,
            "trend_label": trend_label,
        }

    return {"exercises": exercises, "total_sessions": len(logs)}


@tool
async def get_active_cycle(telegram_user_id: int) -> dict:
    """Получить статус активного тренировочного цикла пользователя.

    Возвращает текущую неделю, фазу и информацию о следующей сессии.
    Если активного цикла нет — возвращает {"status": "no_active_cycle"}.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"status": "no_active_cycle", "reason": "user_not_found"}

    row = await _get_active_cycle_data(user_id)
    if not row:
        return {"status": "no_active_cycle"}

    try:
        week_data = row["schedule"]["weeks"][row["current_week"] - 1]
        session_data = week_data["sessions"][row["current_session_index"]]
        total = row["total_weeks"] * row["sessions_per_week"]
        progress_pct = int(row["total_sessions_done"] / total * 100) if total else 0
        sessions_left_this_week = row["sessions_per_week"] - row["current_session_index"]
    except (IndexError, KeyError, TypeError) as exc:
        logger.error("get_active_cycle: corrupted schedule cycle_id=%s: %s", row.get("id"), exc)
        return {
            "status": "active",
            "cycle_id": str(row["id"]),
            "title": row["title"],
            "error": "Программа активна, но возникла ошибка отображения",
        }

    return {
        "status": "active",
        "cycle_id": str(row["id"]),
        "title": row["title"],
        "goal": row["goal"],
        "current_week": row["current_week"],
        "total_weeks": row["total_weeks"],
        "total_sessions_done": row["total_sessions_done"],
        "current_phase": week_data.get("phase"),
        "week_theme": week_data.get("theme"),
        "next_session": {
            "session_index": session_data.get("session_index"),
            "focus": session_data.get("focus"),
            "label": session_data.get("label"),
            "session_number_in_week": row["current_session_index"] + 1,
            "sessions_per_week": row["sessions_per_week"],
            "sessions_left_this_week": sessions_left_this_week,
        },
        "progress_pct": progress_pct,
        "is_last_week": row["current_week"] == row["total_weeks"],
    }


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

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
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
        saved = (
            await client.table("workouts")
            .insert({"user_id": user_id, "title": plan.get("title", focus), "plan": plan})
            .execute()
        )
        plan["id"] = saved.data[0]["id"] if saved.data else None
    except Exception:
        logger.exception("Failed to save workout in get_next_session_plan for user %s", telegram_user_id)

    if cycle_context:
        plan["cycle_context"] = cycle_context
        plan["cycle_id"] = cycle_id

    return plan


@tool
async def get_cycle_summary(telegram_user_id: int) -> dict:
    """Итоги завершённого или текущего тренировочного цикла.

    Возвращает структурированные данные и готовый текст для отображения пользователю.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    client = await get_client()

    # Find most recent cycle (completed or active)
    cycle_result = (
        await client.table("training_cycles")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    cycle_rows = cycle_result.data or []
    if not cycle_rows:
        return {"error": "Нет тренировочных циклов"}

    cycle = cycle_rows[0]
    cycle_id = cycle["id"]

    total_planned = cycle["total_weeks"] * cycle["sessions_per_week"]
    done = cycle["total_sessions_done"]
    completion_rate = round(done / total_planned, 2) if total_planned else 0.0

    # Count logs linked to this cycle
    logs_result = (
        await client.table("workout_logs")
        .select("cycle_week, completed_at")
        .eq("user_id", user_id)
        .eq("cycle_id", cycle_id)
        .order("completed_at")
        .execute()
    )
    linked_logs = logs_result.data or []
    weeks_with_training = len({r.get("cycle_week") for r in linked_logs if r.get("cycle_week")})

    pct = int(completion_rate * 100)
    summary_text = (
        f"🏆 *Цикл завершён! {cycle['title']}*\n\n"
        f"✅ Выполнено {done} из {total_planned} тренировок ({pct}%)\n"
        f"📅 {weeks_with_training} из {cycle['total_weeks']} недель отработано\n\n"
        f"_Отличная работа! Готов к новому вызову?_"
    )

    return {
        "cycle_id": str(cycle_id),
        "title": cycle["title"],
        "goal": cycle["goal"],
        "total_sessions_done": done,
        "total_sessions_planned": total_planned,
        "completion_rate": completion_rate,
        "weeks_completed": weeks_with_training,
        "summary_text": summary_text,
    }


@tool
async def get_cycle_by_id(cycle_id: str) -> dict:
    """Получить данные тренировочного цикла по его ID (активного или завершённого).

    Используется после завершения цикла для предложения нового на основе предыдущего.

    Args:
        cycle_id: UUID цикла из поля cycle_id предыдущего ответа.
    """
    client = await get_client()
    result = (
        await client.table("training_cycles")
        .select("id,title,goal,total_weeks,sessions_per_week,training_type,equipment,status,total_sessions_done")
        .eq("id", cycle_id)
        .single()
        .execute()
    )
    if not result.data:
        return {"error": "Цикл не найден"}
    c = result.data
    total_planned = c["total_weeks"] * c["sessions_per_week"]
    completion_rate = round(c["total_sessions_done"] / total_planned, 2) if total_planned else 0.0
    return {
        "cycle_id": str(c["id"]),
        "title": c["title"],
        "goal": c["goal"],
        "total_weeks": c["total_weeks"],
        "sessions_per_week": c["sessions_per_week"],
        "training_type": c.get("training_type"),
        "equipment": c.get("equipment"),
        "status": c["status"],
        "total_sessions_done": c["total_sessions_done"],
        "total_sessions_planned": total_planned,
        "completion_rate": completion_rate,
    }


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


@tool
async def get_weekly_volume(telegram_user_id: int, weeks_back: int = 4) -> dict:
    """Объём тренировок по группам мышц за последние N недель.

    Показывает количество сетов и тоннаж (кг) по группам мышц в разрезе ISO-недель.
    Помогает выявить мышцы с дефицитом нагрузки.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        weeks_back: За сколько недель считать (по умолчанию 4).
    """
    from agent.tools.exercise_db import EXERCISE_DB

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"weeks": [], "totals": {}, "error": "Пользователь не найден"}

    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(weeks=weeks_back)).isoformat()

    logs_result = (
        await client.table("workout_logs")
        .select("completed_at, performance")
        .eq("user_id", user_id)
        .gte("completed_at", since)
        .order("completed_at")
        .execute()
    )
    logs = logs_result.data or []

    if not logs:
        return {
            "weeks": [],
            "totals": {},
            "message": f"Нет тренировок за последние {weeks_back} недели.",
        }

    # Build exercise → muscle_group map from EXERCISE_DB
    ex_to_group = {_normalize_key(ex.name): ex.muscle_group for ex in EXERCISE_DB}

    # Aggregate by ISO week and muscle group
    # week_data: {iso_week: {group: {"sets": int, "volume_kg": float}}}
    week_data: dict[str, dict[str, dict]] = {}
    totals: dict[str, dict] = {}

    for log in logs:
        completed = log["completed_at"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(completed)
        iso_week = dt.strftime("%G-W%V")  # e.g. "2026-W22"

        if iso_week not in week_data:
            week_data[iso_week] = {}

        for ex in (log.get("performance") or []):
            key = ex.get("key") or _normalize_key(ex.get("name", ""))
            group = ex_to_group.get(key, "other")

            sets = ex.get("sets_done") or 1
            reps = ex.get("reps_done") or 0
            weight = ex.get("weight_kg") or 0.0

            if group not in week_data[iso_week]:
                week_data[iso_week][group] = {"sets": 0, "volume_kg": 0.0}
            week_data[iso_week][group]["sets"] += sets
            week_data[iso_week][group]["volume_kg"] += round(sets * reps * weight, 1)

            if group not in totals:
                totals[group] = {"sets": 0, "volume_kg": 0.0}
            totals[group]["sets"] += sets
            totals[group]["volume_kg"] += round(sets * reps * weight, 1)

    weeks_list = [
        {"iso_week": w, "groups": data}
        for w, data in sorted(week_data.items())
    ]
    return {"weeks": weeks_list, "totals": totals}


@tool
async def adjust_cycle_schedule(
    telegram_user_id: int,
    adjustments: list[dict],
) -> dict:
    """Применить корректировки к расписанию активного тренировочного цикла.

    Меняет фокус и/или метку конкретных сессий в расписании.
    Перед применением сохраняет предыдущую версию расписания в историю.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        adjustments: Список корректировок. Каждый элемент:
            {"week": 3, "session_index": 1, "new_focus": "legs", "new_label": "Ноги (замена)"}
            week — номер недели (1-based), session_index — индекс сессии в неделе (0-based).
            new_focus и new_label — новые значения (оба опциональны, хотя бы одно должно быть).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"status": "error", "message": "Пользователь не найден"}

    client = await get_client()

    # Load active cycle
    cycle_row = (
        await client.table("training_cycles")
        .select("id, schedule, schedule_history")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data
    if not cycle_row:
        return {"status": "error", "message": "Нет активного тренировочного цикла"}

    cycle = cycle_row[0]
    cycle_id = cycle["id"]
    schedule: dict = dict(cycle["schedule"])  # immutable copy
    schedule_history: list = list(cycle.get("schedule_history") or [])

    # Save current schedule snapshot to history before modifying
    schedule_history.append({
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "schedule": schedule,
    })

    applied: list[dict] = []
    errors: list[str] = []

    weeks: list = schedule.get("weeks", [])
    for adj in adjustments:
        week_num = adj.get("week")
        sess_idx = adj.get("session_index")
        new_focus = adj.get("new_focus")
        new_label = adj.get("new_label")

        if week_num is None or sess_idx is None:
            errors.append(f"Пропущены week или session_index в {adj}")
            continue
        if not new_focus and not new_label:
            errors.append(f"Не указаны new_focus или new_label для week={week_num} idx={sess_idx}")
            continue

        try:
            week_data = next(w for w in weeks if w.get("week_number") == week_num)
            session = week_data["sessions"][sess_idx]
        except (StopIteration, IndexError, KeyError, TypeError):
            errors.append(f"Не найдена неделя {week_num} / сессия {sess_idx}")
            continue

        if new_focus:
            session["focus"] = new_focus
        if new_label:
            session["label"] = new_label
        applied.append({"week": week_num, "session_index": sess_idx, "new_focus": new_focus, "new_label": new_label})

    if errors and not applied:
        return {"status": "error", "errors": errors}

    # Persist updated schedule and history
    try:
        await client.table("training_cycles").update({
            "schedule": schedule,
            "schedule_history": schedule_history,
        }).eq("id", cycle_id).execute()
    except Exception:
        logger.exception("adjust_cycle_schedule: DB update failed for cycle %s", cycle_id)
        return {"status": "error", "message": "Не удалось сохранить изменения в БД"}

    return {
        "status": "ok",
        "applied": applied,
        "errors": errors,
        "message": (
            f"Применено {len(applied)} корректировок. "
            f"Предыдущее расписание сохранено в историю (всего {len(schedule_history)} снимков)."
        ),
    }
