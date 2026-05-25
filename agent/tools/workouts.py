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
    suggest_details = done_as_planned and prev_was_as_planned

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

            if equipment_set <= _NO_WEIGHT_EQUIPMENT or weight is None:
                # Bodyweight: suggest more reps
                if reps_done >= hi:
                    note = "↑ +2 повт."
                    next_reps = f"{lo + 2}-{hi + 2}"
                else:
                    note = f"→ цель {reps_done + 1}+ повт."
                    next_reps = f"{lo}-{hi}"
                next_session.append({
                    "name": planned_ex.get("name"),
                    "weight_kg": None,
                    "reps": next_reps,
                    "note": note,
                })
            else:
                increment = _INCREMENT_COMPOUND if is_compound else _INCREMENT_ISOLATION
                if reps_done >= hi:
                    next_weight = weight + increment
                    next_reps = f"{lo}-{hi}"
                    note = f"↑ +{increment}кг"
                elif reps_done >= lo:
                    next_weight = weight
                    next_reps = f"{lo}-{hi}"
                    note = f"→ тот же вес, цель {reps_done + 1}+ повт."
                else:
                    next_weight = weight
                    next_reps = f"{lo}-{hi}"
                    note = f"⚠️ тот же вес, добери до {lo} повт."
                next_session.append({
                    "name": planned_ex.get("name"),
                    "weight_kg": next_weight,
                    "reps": next_reps,
                    "note": note,
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

    await client.table("workout_logs").insert(record).execute()

    return {
        "status": "logged",
        "message": "+1 тренировка в копилку 💪",
        "next_session": next_session,
        "pr_notes": pr_notes,
        "suggest_details": suggest_details,
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


@tool
async def create_training_cycle(
    telegram_user_id: int,
    goal: str,
    weeks: int = 4,
) -> dict:
    """Create a multi-week periodized training mesocycle (4–8 weeks).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        goal: Цель (gain_muscle / lose_weight / strength / endurance).
        weeks: Количество недель (4–8).
    """
    import json
    import re

    from llm.provider import get_llm

    weeks = max(4, min(weeks, 8))

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

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"ПРОТИВОПОКАЗАНИЯ: {listed}. Исключи упражнения с нагрузкой на эти зоны.\n"

    llm = get_llm()
    prompt = (
        f"Составь мезоцикл тренировок на {weeks} недель.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
        f"{injuries_note}"
        f"Принципы:\n"
        f"- Недели 1–{weeks//2}: накопление объёма (умеренная нагрузка)\n"
        f"- Недели {weeks//2+1}–{weeks-1}: интенсификация (+5% веса, -10% объёма)\n"
        f"- Последняя неделя: deload (снижение нагрузки на 30%)\n"
        f"- Двойная прогрессия: сначала повторения до верхней границы диапазона, потом вес\n\n"
        f"Верни JSON:\n"
        f'{{"title": "...", "goal": "...", "weeks": {weeks}, '
        f'"cycle": [{{"week": 1, "theme": "Накопление объёма", '
        f'"sessions": [{{"day": "Понедельник", "focus": "...", '
        f'"exercises": [{{"name": "...", "sets": 3, "reps": "10-12", "rest_seconds": 60}}]}}]}}]}}'
    )

    try:
        response = await llm.ainvoke(prompt)
        raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
    except Exception:
        logger.exception("LLM failed in create_training_cycle for user %s", telegram_user_id)
        return {"error": "Не удалось создать цикл — ошибка LLM"}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        cycle = json.loads(match.group()) if match else {}
    except json.JSONDecodeError:
        logger.warning("JSON parse failed in create_training_cycle, raw=%r", raw[:200])
        cycle = {}

    if not cycle:
        return {"error": "Не удалось разобрать ответ модели"}

    user_id = await _get_user_id(telegram_user_id)
    if user_id:
        try:
            saved = (
                await client.table("workouts")
                .insert({
                    "user_id": user_id,
                    "title": cycle.get("title", f"Цикл: {goal} {weeks} нед."),
                    "plan": cycle,
                })
                .execute()
            )
            cycle["id"] = saved.data[0]["id"] if saved.data else None
        except Exception:
            logger.exception("Failed to save training cycle for user %s", telegram_user_id)

    return cycle


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

        exercises[key] = {
            "display_name": display_name,
            "history": [
                {"date": p["date"], "weight_kg": p.get("weight_kg"), "reps_done": p.get("reps_done")}
                for p in history_points
            ],
            "trend": trend,
            "next_target": next_target,
            "sessions_count": len(history_points),
        }

    return {"exercises": exercises, "total_sessions": len(logs)}


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
