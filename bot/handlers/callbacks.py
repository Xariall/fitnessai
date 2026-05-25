import contextlib
import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.chat import run_agent
from bot.handlers.commands import _show_profile
from bot.handlers.direct import (
    WeightFSM,
    show_progress_dynamics,
    show_stats,
    show_today_summary,
    show_workout_history,
)
from bot.keyboards.main import (
    main_menu_keyboard,
    nutrition_submenu_keyboard,
    progress_submenu_keyboard,
    workout_submenu_keyboard,
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
    "log_workout": "Запиши мою тренировку как выполненную",
    "nutrition_plan": "Составь план питания на день",
}

_AFTER_AGENT_PROMPTS = {
    "add_food": "Хочу записать еду — что я ел?",
    "log_workout": "Запиши мою тренировку как выполненную",
    "weekly": "Покажи итог моей недели — тренировки, питание, вес",
    "recovery": "Вызови get_recovery_overview и покажи статус восстановления по всем группам мышц",
    "hydration": "Рассчитай мою норму воды на сегодня",
}


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Убирает inline-клавиатуру у сообщения с нажатой кнопкой."""
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)


# ── Навигация ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:home")
async def handle_menu_home(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await callback.message.answer("Главное меню 🏠", reply_markup=main_menu_keyboard())


# ── Прямые (без LLM) ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "submenu:today_summary")
async def handle_today_summary(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await show_today_summary(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:workout_history")
async def handle_workout_history(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await show_workout_history(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:my_dynamics")
async def handle_my_dynamics(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await show_progress_dynamics(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:log_measurement")
async def handle_log_measurement(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await state.set_state(WeightFSM.waiting_for_weight)
    await callback.message.answer(
        "Сколько ты весишь сейчас? (в кг, например: `82.5`)",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "quick:profile")
async def handle_quick_profile(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await _show_profile(callback.message, telegram_user_id=callback.from_user.id)


# ── С LLM (streaming через run_agent) ─────────────────────────────────────────

@router.callback_query(F.data.startswith("submenu:"))
async def handle_submenu(callback: CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    prompt = _SUBMENU_AGENT_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    await run_agent(callback, prompt)


@router.callback_query(F.data.startswith("quick:"))
async def handle_quick_action(callback: CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    prompt = _QUICK_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    await run_agent(callback, prompt)


# ── After-action контекстные кнопки ───────────────────────────────────────────

@router.callback_query(F.data == "after:stats")
async def handle_after_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await show_stats(callback.message, callback.from_user.id)


@router.callback_query(F.data == "after:dynamics")
async def handle_after_dynamics(callback: CallbackQuery) -> None:
    await callback.answer()
    await _strip_keyboard(callback)
    await show_progress_dynamics(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("after:"))
async def handle_after_action(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]

    if action == "log_measurement":
        await callback.answer()
        await _strip_keyboard(callback)
        await state.set_state(WeightFSM.waiting_for_weight)
        await callback.message.answer(
            "Сколько ты весишь сейчас? (в кг, например: `82.5`)",
            parse_mode="Markdown",
        )
        return

    prompt = _AFTER_AGENT_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer()
    await run_agent(callback, prompt)


@router.callback_query()
async def handle_callback_fallback(callback: CallbackQuery) -> None:
    await callback.answer()
