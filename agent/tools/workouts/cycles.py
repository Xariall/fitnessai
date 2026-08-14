"""Жизненный цикл тренировочного цикла: черновик, создание, статус, корректировка расписания."""
import logging
from datetime import date, datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import execute, fetch, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _get_active_cycle_data

logger = logging.getLogger(__name__)

# Rate limiting for cycle generation: max 3 per user per day (in-memory)
_MAX_CYCLES_PER_DAY = 3
_cycle_gen_counts: dict[tuple[int, str], int] = {}


def _today_str() -> str:
    return date.today().isoformat()


def _cycle_gen_allowed(telegram_user_id: int) -> bool:
    return _cycle_gen_counts.get((telegram_user_id, _today_str()), 0) < _MAX_CYCLES_PER_DAY


def _cycle_gen_increment(telegram_user_id: int) -> int:
    key = (telegram_user_id, _today_str())
    _cycle_gen_counts[key] = _cycle_gen_counts.get(key, 0) + 1
    return _cycle_gen_counts[key]


@tool
async def generate_cycle_preview(
    telegram_user_id: int,
    goal: str,
    weeks: int = 6,
    sessions_per_week: int = 3,
    training_type: Optional[str] = None,
    equipment: Optional[str] = None,
) -> dict:
    """Сгенерировать ЧЕРНОВИК тренировочного цикла для предпросмотра.

    Выполняет всю логику генерации (LLM + валидация), но НЕ сохраняет в базу данных.
    Используй этот инструмент ПЕРЕД create_training_cycle — сначала покажи пользователю
    план и дождись подтверждения, затем вызывай create_training_cycle.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        goal: Цель (gain_muscle / lose_weight / strength / endurance).
        weeks: Количество недель (4–8).
        sessions_per_week: Тренировок в неделю (2–5).
        training_type: Стиль тренинга (strength / hypertrophy / functional / mixed).
        equipment: Оборудование (gym / home_dumbbells / bodyweight).
    """
    import json
    import re

    from pydantic import ValidationError

    from db.models import TrainingCycleSchedule
    from llm.provider import get_llm

    weeks = max(4, min(weeks, 8))
    sessions_per_week = max(2, min(sessions_per_week, 5))

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # Check for existing active cycle (informational only — draft never replaces)
    existing = await fetchrow(
        "SELECT id, title, current_week, total_weeks FROM training_cycles "
        "WHERE user_id = $1 AND status = 'active' LIMIT 1",
        user_id,
    )

    profile = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    ) or {}
    injuries: list[str] = profile.get("injuries") or []

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"ПРОТИВОПОКАЗАНИЯ: {listed}. Исключи фокусы с нагрузкой на эти зоны.\n"

    training_type_note = f"Тип тренинга: {training_type}.\n" if training_type else ""
    equipment_note = f"Оборудование: {equipment}.\n" if equipment else ""

    from agent.prompts.system import CYCLE_PHASE_RULES

    _GOAL_GUIDELINES = {
        "gain_muscle": "Гипертрофия: 12–20 сетов/группа/нед, RIR 1–3, приоритет компаундам.",
        "lose_weight": "Жиросжигание: 6–12 сетов/группа/нед (поддержание мышц), RIR 2–4.",
        "strength": "Сила: 5–10 сетов/группа/нед, RIR 0–2, вес 80–90% 1RM.",
        "endurance": "Выносливость: 8–15 сетов/группа/нед, RIR 2–3, повторения 12–20.",
    }
    goal_guideline = _GOAL_GUIDELINES.get(goal, "")

    llm = get_llm()
    prompt = (
        f"{CYCLE_PHASE_RULES}\n\n"
        f"---\n"
        f"Составь расписание тренировочного цикла на {weeks} недель, {sessions_per_week} тренировки/нед.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
        f"{training_type_note}{equipment_note}{injuries_note}"
        f"\nОриентиры: {goal_guideline}\n"
        f"Правила:\n"
        f"- Баланс push/pull/legs за неделю (не перегружай одну группу)\n"
        f"- Компаунды первыми в каждой сессии, изоляция — в конце\n"
        f"- Каждая группа мышц — минимум 2 раза в неделю для оптимального стимула\n\n"
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

    parsed: dict = {}
    for attempt in range(2):
        try:
            response = await llm.ainvoke(prompt)
            raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
        except Exception:
            logger.exception("LLM failed in generate_cycle_preview for user %s", telegram_user_id)
            return {"error": "Не удалось создать черновик — ошибка LLM"}

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            parsed = json.loads(match.group()) if match else {}
        except json.JSONDecodeError:
            if attempt == 1:
                return {"error": "Не удалось разобрать ответ модели"}
            continue

        if not parsed or "weeks" not in parsed:
            if attempt == 1:
                return {"error": "Не удалось разобрать ответ модели"}
            continue

        try:
            TrainingCycleSchedule.model_validate({"weeks": parsed["weeks"]})
            break
        except ValidationError as e:
            logger.warning("preview schedule validation failed attempt %d: %s", attempt, e)
            if attempt == 1:
                return {"error": f"Не удалось сгенерировать корректное расписание: {e}"}
            prompt += f"\n\nПредыдущий ответ не прошёл валидацию: {e}\nПопробуй ещё раз строго по формату."

    title = parsed.get("title") or f"Цикл {weeks} нед."

    # Format compact preview grouped by phase
    _PHASE_LABELS = {
        "accumulation": "Накопление",
        "intensification": "Интенсификация",
        "deload": "Разгрузка",
    }
    weeks_data: list[dict] = parsed.get("weeks", [])
    phase_groups: list[tuple] = []  # (phase, start_wk, end_wk, theme, session_labels)
    for wk in weeks_data:
        wk_num = wk.get("week_number", 0)
        phase = wk.get("phase", "accumulation")
        theme = wk.get("theme", "")
        labels = [s.get("label", "") for s in wk.get("sessions", [])]
        if phase_groups and phase_groups[-1][0] == phase:
            g = phase_groups[-1]
            phase_groups[-1] = (g[0], g[1], wk_num, g[3], g[4])
        else:
            phase_groups.append((phase, wk_num, wk_num, theme, labels))

    def _escape_md(text: str) -> str:
        return text.replace("_", "\\_").replace("*", "\\*")

    phase_lines = []
    for phase, start, end, theme, labels in phase_groups:
        phase_label = _PHASE_LABELS.get(phase, phase)
        wk_range = f"Нед. {start}" if start == end else f"Нед. {start}–{end}"
        sessions_str = " → ".join(_escape_md(lb) for lb in labels)
        phase_lines.append(f"• {wk_range} *({phase_label})*: {theme}\n  _{sessions_str}_")

    type_label = {
        "strength": "Силовой", "hypertrophy": "На массу",
        "functional": "Функциональный", "mixed": "Смешанный",
    }.get(training_type or "", training_type or "смешанный")
    equip_label = {
        "gym": "Зал", "home_dumbbells": "Дом + гантели", "bodyweight": "Без инвентаря",
    }.get(equipment or "", equipment or "зал")

    preview_text = (
        f"📅 *{title}*\n"
        f"🔁 {weeks} нед · {sessions_per_week} тр/нед · {type_label} · {equip_label}\n\n"
        + "\n".join(phase_lines)
    )

    return {
        "status": "draft_ready",
        "title": title,
        "preview_text": preview_text,
        "weeks": weeks,
        "sessions_per_week": sessions_per_week,
        "training_type": training_type,
        "equipment": equipment,
        "goal": goal,
        "has_active_cycle": bool(existing),
    }


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

    # Rate limit: max 3 cycle creations per day per user
    if not _cycle_gen_allowed(telegram_user_id):
        return {
            "error": (
                f"Достигнут дневной лимит создания программ ({_MAX_CYCLES_PER_DAY}/день). "
                "Попробуй завтра."
            )
        }

    weeks = max(4, min(weeks, 8))
    sessions_per_week = max(2, min(sessions_per_week, 5))

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # Check for existing active cycle before doing anything expensive
    existing = await fetchrow(
        "SELECT id, title, current_week, total_weeks FROM training_cycles "
        "WHERE user_id = $1 AND status = 'active' LIMIT 1",
        user_id,
    )
    if existing and not force_replace:
        c = existing
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

    profile = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    ) or {}
    injuries: list[str] = profile.get("injuries") or []

    injuries_note = ""
    if injuries:
        from agent.tools.exercise_db import injury_label
        listed = ", ".join(injury_label(i) for i in injuries)
        injuries_note = f"ПРОТИВОПОКАЗАНИЯ: {listed}. Исключи фокусы с нагрузкой на эти зоны.\n"

    training_type_note = f"Тип тренинга: {training_type}.\n" if training_type else ""
    equipment_note = f"Оборудование: {equipment}.\n" if equipment else ""

    from agent.prompts.system import CYCLE_PHASE_RULES

    # Evidence-based volume guidelines per goal (Schoenfeld, Israetel)
    _GOAL_GUIDELINES = {
        "gain_muscle": "Гипертрофия: 12–20 сетов/группа/нед, RIR 1–3, приоритет компаундам.",
        "lose_weight": "Жиросжигание: 6–12 сетов/группа/нед (поддержание мышц), RIR 2–4.",
        "strength": "Сила: 5–10 сетов/группа/нед, RIR 0–2, вес 80–90% 1RM.",
        "endurance": "Выносливость: 8–15 сетов/группа/нед, RIR 2–3, повторения 12–20.",
    }
    goal_guideline = _GOAL_GUIDELINES.get(goal, "")

    llm = get_llm()
    prompt = (
        f"{CYCLE_PHASE_RULES}\n\n"
        f"---\n"
        f"Составь расписание тренировочного цикла на {weeks} недель, {sessions_per_week} тренировки/нед.\n"
        f"Профиль: вес {profile.get('weight_kg')} кг, цель: {goal}, "
        f"активность: {profile.get('activity_level')}.\n"
        f"{training_type_note}{equipment_note}{injuries_note}"
        f"\nОриентиры: {goal_guideline}\n"
        f"Правила:\n"
        f"- Баланс push/pull/legs за неделю (не перегружай одну группу)\n"
        f"- Компаунды первыми в каждой сессии, изоляция — в конце\n"
        f"- Каждая группа мышц — минимум 2 раза в неделю для оптимального стимула\n\n"
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
        await execute(
            "UPDATE training_cycles SET status = 'completed' WHERE user_id = $1 AND status = 'active'",
            user_id,
        )
    except Exception as e:
        logger.exception("Failed to deactivate old cycle for user %s: %s", telegram_user_id, e)
        return {"error": "Не удалось завершить старый цикл. Попробуй ещё раз через 10 сек."}

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
            "current_week": 1,
            "current_session_index": 0,
        }
        if training_type:
            insert_data["training_type"] = training_type
        if equipment:
            insert_data["equipment"] = equipment

        columns = list(insert_data.keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        args = [insert_data[col] for col in columns]
        saved = await fetchrow(
            f"INSERT INTO training_cycles ({col_list}) VALUES ({placeholders}) RETURNING id",
            *args,
        )
        cycle_id = saved["id"] if saved else None
        _cycle_gen_increment(telegram_user_id)
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

    _goal_display_map = {
        "gain_muscle": "набор массы",
        "lose_weight": "похудение",
        "maintain": "поддержание формы",
        "strength": "сила",
        "endurance": "выносливость",
        "flexibility": "гибкость",
    }
    return {
        "cycle_id": cycle_id,
        "title": title,
        "goal": goal,
        "goal_display": _goal_display_map.get(goal, goal),
        "total_weeks": weeks,
        "sessions_per_week": sessions_per_week,
        "training_type": training_type,
        "equipment": equipment,
        "week_1_theme": parsed["weeks"][0].get("theme") if parsed["weeks"] else "",
        "next_session": next_session,
        "schedule": schedule,
    }


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

    _goal_labels = {
        "lose_weight": "Похудение",
        "gain_muscle": "Набор мышечной массы",
        "maintain": "Поддержание формы",
        "strength": "Сила",
        "endurance": "Выносливость",
    }
    return {
        "status": "active",
        "cycle_id": str(row["id"]),
        "title": row["title"],
        "goal": _goal_labels.get(row["goal"], row["goal"]),
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
async def get_cycle_summary(telegram_user_id: int) -> dict:
    """Итоги завершённого или текущего тренировочного цикла.

    Возвращает структурированные данные и готовый текст для отображения пользователю.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # Find most recent cycle (completed or active)
    cycle = await fetchrow(
        "SELECT * FROM training_cycles WHERE user_id = $1 "
        "ORDER BY created_at DESC LIMIT 1",
        user_id,
    )
    if not cycle:
        return {"error": "Нет тренировочных циклов"}

    cycle_id = cycle["id"]

    total_planned = cycle["total_weeks"] * cycle["sessions_per_week"]
    done = cycle["total_sessions_done"]
    completion_rate = round(done / total_planned, 2) if total_planned else 0.0

    # Count logs linked to this cycle
    linked_logs = await fetch(
        "SELECT cycle_week, completed_at FROM workout_logs "
        "WHERE user_id = $1 AND cycle_id = $2 ORDER BY completed_at",
        user_id, cycle_id,
    )
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
    c = await fetchrow(
        "SELECT id, title, goal, total_weeks, sessions_per_week, training_type, "
        "equipment, status, total_sessions_done FROM training_cycles WHERE id = $1",
        cycle_id,
    )
    if not c:
        return {"error": "Цикл не найден"}
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

    # Load active cycle
    cycle = await fetchrow(
        "SELECT id, schedule, schedule_history FROM training_cycles "
        "WHERE user_id = $1 AND status = 'active' "
        "ORDER BY created_at DESC LIMIT 1",
        user_id,
    )
    if not cycle:
        return {"status": "error", "message": "Нет активного тренировочного цикла"}

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
        await execute(
            "UPDATE training_cycles SET schedule = $1, schedule_history = $2 WHERE id = $3",
            schedule, schedule_history, cycle_id,
        )
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
