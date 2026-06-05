import logging
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.chat import run_agent
from bot.handlers.direct import (
    InputModeFSM,
    WeightFSM,
    show_progress_dynamics,
    show_stats,
    show_today_summary,
    show_workout_history,
)
from bot.helpers import clear_fsm_keep_nav, send_and_track
from bot.keyboards.main import (
    cycle_complete_keyboard,
    no_active_cycle_keyboard,
    nutrition_submenu_keyboard,
    progress_submenu_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

_QUICK_PROMPTS = {
    "nutrition_plan": "Составь мне план питания на сегодня",
    "workout_plan": "Составь мне тренировку на сегодня",
    "progress": "Покажи мой прогресс за последний месяц",
}

_SUBMENU_AGENT_PROMPTS = {
    "my_plan": "Составь мне тренировку на сегодня",
    "nutrition_plan": "Составь план питания на день",
    "create_cycle": (
        "Начни диалог для создания программы тренировок. "
        "Следуй инструкции «Создание тренировочного цикла» из системного промпта — "
        "задай 3 вопроса одним сообщением и жди ответа пользователя."
    ),
    "train_today": (
        "Используй get_next_session_plan чтобы получить следующую сессию по активному циклу. "
        "Если активного цикла нет — только скажи пользователю что нет активной программы тренировок "
        "и предложи создать. Не генерируй и не предлагай случайные тренировки без программы."
    ),
    "active_cycle": (
        "Используй get_active_cycle чтобы показать статус активной программы."
    ),
}

_AFTER_AGENT_PROMPTS = {
    "weekly": "Покажи итог моей недели — тренировки, питание, вес",
    "recovery": "Вызови get_recovery_overview и покажи статус восстановления по всем группам мышц",
    "hydration": "Рассчитай мою норму воды на сегодня",
}


# ── Навигация ──────────────────────────────────────────────────────────────────

_BACK_TARGETS = {
    "nutrition": ("🥗 Питание",  nutrition_submenu_keyboard),
    "progress":  ("📊 Прогресс", progress_submenu_keyboard),
}


@router.callback_query(F.data == "menu:home")
async def handle_menu_home(callback: CallbackQuery) -> None:
    await callback.answer("Главное меню открыто")


@router.callback_query(F.data == "back:workout")
async def handle_back_workout(callback: CallbackQuery, state: FSMContext) -> None:
    from bot.helpers import get_workout_section
    await callback.answer()
    text, kb = await get_workout_section(callback.from_user.id)
    await send_and_track(callback, text, state, reply_markup=kb, allow_edit=True)


@router.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery, state: FSMContext) -> None:
    section = callback.data.split(":", 1)[1]
    if section not in _BACK_TARGETS:
        await callback.answer()
        return
    title, kb_fn = _BACK_TARGETS[section]
    await callback.answer()
    await send_and_track(callback, title, state, reply_markup=kb_fn(), allow_edit=True)


# ── Прямые (без LLM) ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "submenu:today_summary")
async def handle_today_summary(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_today_summary(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == "submenu:workout_history")
async def handle_workout_history(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_workout_history(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == "submenu:my_dynamics")
async def handle_my_dynamics(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_progress_dynamics(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == "submenu:log_measurement")
async def handle_log_measurement(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_fsm_keep_nav(state)
    await state.set_state(WeightFSM.waiting_for_weight)
    await send_and_track(
        callback,
        "Сколько ты весишь сейчас? (в кг, например: `82.5`)",
        state,
    )


@router.callback_query(F.data == "quick:profile")
async def handle_quick_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    from bot.handlers.commands import get_profile_text
    text = await get_profile_text(telegram_user_id=callback.from_user.id)
    await send_and_track(callback, text, state)


# ── FSM-ввод: еда и тренировка ────────────────────────────────────────────────

@router.callback_query(F.data == "after:add_food")
async def handle_add_food_input(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_fsm_keep_nav(state)
    await state.set_state(InputModeFSM.waiting_for_input)
    await state.update_data(created_at=time.time(), input_mode="add_food")
    await send_and_track(
        callback,
        "Что ты сегодня ел? 🍽\n"
        "Напиши продукты и вес — например: «гречка 200 г, курица 150 г, 2 яйца»\n\n"
        "_Для отмены нажми любую кнопку меню._",
        state,
    )


@router.callback_query(F.data.in_({"after:log_workout", "submenu:log_workout"}))
async def handle_log_workout_input(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_fsm_keep_nav(state)
    await state.set_state(InputModeFSM.waiting_for_input)
    await state.update_data(created_at=time.time(), input_mode="log_workout")
    await send_and_track(
        callback,
        "Как прошла тренировка? 💪\n"
        "Напиши «всё по плану» или перечисли упражнения с весами — "
        "например: «жим 80 кг × 10, присед 100 кг × 8»\n\n"
        "_Для отмены нажми любую кнопку меню._",
        state,
    )


# ── С LLM (streaming через run_agent) ─────────────────────────────────────────

@router.callback_query(F.data == "submenu:active_cycle")
async def handle_active_cycle(callback: CallbackQuery, state: FSMContext) -> None:
    """Показывает статус программы; если нет — сразу даёт кнопку создать."""
    await callback.answer()
    response = await run_agent(callback, _SUBMENU_AGENT_PROMPTS["active_cycle"], state=state)
    if response and ("нет программы" in response.lower() or "no_active_cycle" in response.lower()
                     or "нет активн" in response.lower() or "программы нет" in response.lower()
                     or "напиши" in response.lower()):
        follow = await callback.message.answer(
            "_Нажми кнопку — создам программу под тебя:_",
            parse_mode="Markdown",
            reply_markup=no_active_cycle_keyboard(),
        )
        await state.update_data(last_bot_msg_id=follow.message_id)


@router.callback_query(F.data == "submenu:train_today")
async def handle_train_today(callback: CallbackQuery, state: FSMContext) -> None:
    """Показывает следующую сессию из цикла; если нет цикла — предлагает создать."""
    await callback.answer()
    response = await run_agent(callback, _SUBMENU_AGENT_PROMPTS["train_today"], state=state)

    if response and ("нет программы" in response.lower() or "нет активн" in response.lower()
                     or "программы нет" in response.lower() or "создай программу" in response.lower()):
        follow = await callback.message.answer(
            "_Нажми кнопку — создам программу под тебя:_",
            parse_mode="Markdown",
            reply_markup=no_active_cycle_keyboard(),
        )
        await state.update_data(last_bot_msg_id=follow.message_id)


@router.callback_query(F.data.startswith("submenu:"))
async def handle_submenu(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    prompt = _SUBMENU_AGENT_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    response = await run_agent(callback, prompt, state=state)
    if response and "программа создана" in response.lower():
        from bot.keyboards.main import after_cycle_create_keyboard
        from bot.helpers import send_and_track
        await send_and_track(callback, "Готов начать? Нажми кнопку:", state, reply_markup=after_cycle_create_keyboard())


@router.callback_query(F.data.startswith("quick:"))
async def handle_quick_action(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    prompt = _QUICK_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    await run_agent(callback, prompt, state=state)


# ── After-action контекстные кнопки ───────────────────────────────────────────

@router.callback_query(F.data == "after:stats")
async def handle_after_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_stats(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == "after:dynamics")
async def handle_after_dynamics(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_progress_dynamics(callback.message, callback.from_user.id, state)


@router.callback_query(F.data.startswith("after:"))
async def handle_after_action(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]

    if action == "log_measurement":
        await callback.answer()
        await clear_fsm_keep_nav(state)
        await state.set_state(WeightFSM.waiting_for_weight)
        await send_and_track(
            callback,
            "Сколько ты весишь сейчас? (в кг, например: `82.5`)",
            state,
        )
        return

    prompt = _AFTER_AGENT_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    await run_agent(callback, prompt, state=state)


@router.callback_query(F.data.startswith("cycle:start_new"))
async def handle_cycle_start_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":", 2)
    cycle_id = parts[2] if len(parts) == 3 else ""
    if cycle_id:
        prompt = (
            f"Пользователь хочет начать новый цикл. Предыдущий цикл id={cycle_id}. "
            "Вызови get_cycle_by_id чтобы узнать параметры предыдущего цикла, "
            "предложи те же параметры (стиль, оборудование, частота, недели) как дефолт — "
            "но явно укажи что каждый можно изменить. "
            "После подтверждения создай новый цикл."
        )
    else:
        prompt = (
            "Пользователь хочет начать новый цикл. "
            "Предложи параметры нового цикла: стиль тренинга, оборудование, частота, недели. "
            "Явно укажи что каждый можно изменить. "
            "После подтверждения создай новый цикл."
        )
    await run_agent(callback, prompt, state=state)


@router.callback_query(F.data == "cycle:confirm_draft")
async def handle_cycle_confirm_draft(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь подтвердил создание программы — создаём с теми же параметрами."""
    await callback.answer()
    data = await state.get_data()
    params = data.get("cycle_draft_params") or {}
    if not params:
        await callback.message.answer("Параметры программы не найдены. Попробуй создать ещё раз.")
        return
    weeks = params.get("weeks", 6)
    sessions_per_week = params.get("sessions_per_week", 3)
    training_type = params.get("training_type", "mixed")
    equipment = params.get("equipment", "gym")
    goal = params.get("goal", "gain_muscle")
    force_part = " Если есть активный цикл — замени его (force_replace=True)." if params.get("has_active_cycle") else ""
    prompt = (
        f"Пользователь подтвердил создание программы. Вызови create_training_cycle с параметрами: "
        f"goal={goal}, weeks={weeks}, sessions_per_week={sessions_per_week}, "
        f"training_type={training_type}, equipment={equipment}, force_replace=False.{force_part}"
    )
    response = await run_agent(callback, prompt, state=state)
    if response and "программа создана" in response.lower():
        from bot.keyboards.main import after_cycle_create_keyboard
        from bot.helpers import send_and_track
        await send_and_track(callback, "Готов начать? Нажми кнопку:", state, reply_markup=after_cycle_create_keyboard())
    await state.update_data(cycle_draft_params=None)


@router.callback_query(F.data == "cycle:regenerate_draft")
async def handle_cycle_regenerate_draft(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь хочет другой вариант программы."""
    await callback.answer()
    data = await state.get_data()
    params = data.get("cycle_draft_params") or {}
    if not params:
        await callback.message.answer("Параметры программы не найдены. Попробуй создать ещё раз.")
        return
    weeks = params.get("weeks", 6)
    sessions_per_week = params.get("sessions_per_week", 3)
    training_type = params.get("training_type", "mixed")
    equipment = params.get("equipment", "gym")
    goal = params.get("goal", "gain_muscle")
    prompt = (
        f"Пересоздай черновик программы с теми же параметрами: "
        f"goal={goal}, weeks={weeks}, sessions_per_week={sessions_per_week}, "
        f"training_type={training_type}, equipment={equipment}. "
        f"Вызови generate_cycle_preview с этими параметрами."
    )
    await run_agent(callback, prompt, state=state)


@router.callback_query()
async def handle_callback_fallback(callback: CallbackQuery) -> None:
    await callback.answer()
