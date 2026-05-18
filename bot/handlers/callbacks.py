import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
from bot.handlers.commands import _show_profile
from bot.handlers.direct import (
    WeightFSM,
    show_progress_dynamics,
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


async def _invoke_agent(callback: CallbackQuery, prompt: str) -> None:
    telegram_user_id = callback.from_user.id
    try:
        result = await agent_graph.ainvoke(
            {
                "messages": [HumanMessage(content=prompt)],
                "user_profile": {},
                "telegram_user_id": telegram_user_id,
            },
            config={"configurable": {"thread_id": str(telegram_user_id)}},
        )
        reply = result["messages"][-1].content
    except Exception:
        logger.exception("Agent error for user %s", telegram_user_id)
        reply = "Что-то пошло не так. Попробуй снова."

    try:
        await callback.message.answer(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.answer(reply)


@router.callback_query(F.data == "menu:home")
async def handle_menu_home(callback: CallbackQuery) -> None:
    await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
    await callback.answer()


# ── Direct (без LLM) ──────────────────────────

@router.callback_query(F.data == "submenu:today_summary")
async def handle_today_summary(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_today_summary(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:workout_history")
async def handle_workout_history(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_workout_history(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:my_dynamics")
async def handle_my_dynamics(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_progress_dynamics(callback.message, callback.from_user.id)


@router.callback_query(F.data == "submenu:log_measurement")
async def handle_log_measurement(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(WeightFSM.waiting_for_weight)
    await callback.message.answer(
        "Сколько ты весишь сейчас? (в кг, например: `82.5`)",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "quick:profile")
async def handle_quick_profile(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_profile(callback.message)


# ── С LLM ────────────────────────────────────

@router.callback_query(F.data.startswith("submenu:"))
async def handle_submenu(callback: CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    prompt = _SUBMENU_AGENT_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer("⏳")
    await _invoke_agent(callback, prompt)


@router.callback_query(F.data.startswith("quick:"))
async def handle_quick_action(callback: CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    prompt = _QUICK_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return
    await callback.answer("⏳")
    await _invoke_agent(callback, prompt)


@router.callback_query()
async def handle_callback_fallback(callback: CallbackQuery) -> None:
    await callback.answer()
