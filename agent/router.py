"""Роутинг запросов между специализированными под-агентами.

Вместо одного planner'а со всеми 35 tools и всем системным промптом сразу
(см. agent/nodes.py:planner), каждый ход маршрутизируется в один из пяти
доменов — у каждого свой узкий список инструментов и свой кусок промпта
(agent/prompts/{workout,nutrition,progress,motivation,general}.py).

Активируется флагом settings.enable_subagent_router (config.py). Пока флаг
выключен, agent/graph.py использует старый плоский путь без изменений.
"""
import logging

from langchain_core.messages import HumanMessage

from agent.prompts.general import GENERAL_RULES
from agent.prompts.motivation import MOTIVATION_RULES
from agent.prompts.nutrition import NUTRITION_RULES
from agent.prompts.progress import PROGRESS_RULES
from agent.prompts.shared import build_domain_prompt
from agent.prompts.workout import WORKOUT_RULES
from agent.tools.motivation import generate_motivation_meme, send_motivation
from agent.tools.nutrition import (
    calculate_daily_calories,
    calculate_hydration,
    check_nutrition_adjustment,
    delete_log_entry,
    generate_nutrition_plan,
    get_daily_nutrition_summary,
    get_food_info,
    get_nutrition_preferences,
    get_workout_nutrition_protocol,
    log_food,
    save_nutrition_preferences,
)
from agent.tools.profile import get_user_profile, update_user_profile
from agent.tools.progress import get_progress_summary, get_weekly_summary, log_progress
from agent.tools.workouts import (
    adjust_cycle_schedule,
    check_recovery_status,
    create_training_cycle,
    find_exercises,
    generate_cycle_preview,
    generate_weekly_debrief,
    generate_workout_plan,
    get_active_cycle,
    get_cycle_by_id,
    get_cycle_summary,
    get_exercise_history,
    get_next_session_plan,
    get_recovery_overview,
    get_training_roadmap,
    get_weekly_volume,
    get_workout_history,
    log_workout,
    replace_workout_exercise,
    update_user_injuries,
)

logger = logging.getLogger(__name__)

# Совпадают 1-в-1 с ключами agent.chat_modes.MODES — явный выбор режима
# пользователем маршрутизирует напрямую, без LLM-классификации.
DOMAINS: tuple[str, ...] = ("workout", "nutrition", "progress", "motivation", "general")

TOOLS_BY_DOMAIN: dict[str, list] = {
    "workout": [
        generate_workout_plan,
        log_workout,
        get_workout_history,
        get_exercise_history,
        get_training_roadmap,
        get_weekly_volume,
        find_exercises,
        check_recovery_status,
        get_recovery_overview,
        generate_cycle_preview,
        create_training_cycle,
        get_active_cycle,
        get_next_session_plan,
        get_cycle_summary,
        get_cycle_by_id,
        replace_workout_exercise,
        update_user_injuries,
        adjust_cycle_schedule,
        generate_weekly_debrief,
    ],
    "nutrition": [
        calculate_daily_calories,
        generate_nutrition_plan,
        log_food,
        delete_log_entry,
        get_daily_nutrition_summary,
        get_food_info,
        get_workout_nutrition_protocol,
        check_nutrition_adjustment,
        calculate_hydration,
        get_nutrition_preferences,
        save_nutrition_preferences,
    ],
    "progress": [
        log_progress,
        get_progress_summary,
        get_weekly_summary,
    ],
    "motivation": [
        send_motivation,
        generate_motivation_meme,
    ],
    # Катчол при неоднозначной классификации: профиль + пересчёт нормы КБЖУ
    # после обновления профиля, плюс read-only сводки для общих вопросов
    # о дне/статусе без полного доступа к tools своих доменов
    # (см. agent/prompts/general.py GENERAL_RULES).
    "general": [
        get_user_profile,
        update_user_profile,
        calculate_daily_calories,
        get_daily_nutrition_summary,
        get_progress_summary,
        get_workout_history,
    ],
}

DOMAIN_PROMPTS: dict[str, str] = {
    "workout": build_domain_prompt(WORKOUT_RULES),
    "nutrition": build_domain_prompt(NUTRITION_RULES),
    "progress": build_domain_prompt(PROGRESS_RULES),
    "motivation": build_domain_prompt(MOTIVATION_RULES),
    "general": build_domain_prompt(GENERAL_RULES),
}


_CLASSIFY_PROMPT = """\
Определи к какому домену относится последнее сообщение пользователя фитнес-бота.
Ответь ОДНИМ словом, без пояснений — точно одним из: workout, nutrition, progress, motivation, general.

workout — тренировки, упражнения, программы, восстановление, травмы
nutrition — питание, КБЖУ, еда, гидратация
progress — вес, замеры, динамика, недельные итоги
motivation — мотивация, лень, усталость, поддержка
general — профиль, смена цели/возраста/веса как факта, всё остальное неоднозначное

Сообщение пользователя: {message}

Домен:"""


async def classify_domain(user_message: str) -> str:
    """LLM-классификация домена для general-режима. Дешёвый вызов без thinking.

    При ошибке LLM или нераспознанном ответе — безопасный откат на "general"
    (общий катчол с доступом к профилю), а не падение хода.
    """
    from llm.provider import get_llm

    llm = get_llm()
    try:
        response = await llm.ainvoke([HumanMessage(content=_CLASSIFY_PROMPT.format(message=user_message))])
        guess = (response.content or "").strip().lower()
    except Exception:
        logger.exception("classify_domain: LLM call failed, falling back to general")
        return "general"

    for domain in DOMAINS:
        if domain in guess:
            return domain
    logger.warning("classify_domain: unrecognized model output %r, falling back to general", guess[:80])
    return "general"


async def resolve_domain(telegram_user_id: int, user_message: str) -> str:
    """Определяет домен для текущего хода.

    Явный режим пользователя (кнопки 🏋️/🥗/📊/💪 из chat_modes) имеет приоритет
    и не требует LLM-вызова. В режиме "general" — LLM-классификация по тексту.
    """
    from agent.chat_modes import get_mode

    mode_key = get_mode(telegram_user_id).key
    if mode_key != "general":
        return mode_key
    return await classify_domain(user_message)
