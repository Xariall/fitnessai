import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
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
    "profile": "Покажи мой профиль",
}

_SUBMENU_PROMPTS = {
    "my_plan": "Составь мне тренировку на сегодня",
    "log_workout": "Запиши мою тренировку как выполненную",
    "workout_history": "Покажи историю моих тренировок",
    "nutrition_plan": "Составь план питания на день",
    "today_summary": "Что я съел сегодня? Покажи итог за день",
    "log_measurement": "Хочу записать замер веса",
    "my_dynamics": "Покажи мою динамику веса за последний месяц",
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
        reply = "Произошла ошибка. Попробуй ещё раз."

    try:
        await callback.message.answer(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.answer(reply)


@router.callback_query(F.data == "menu:home")
async def handle_menu_home(callback: CallbackQuery) -> None:
    await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("submenu:"))
async def handle_submenu(callback: CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    prompt = _SUBMENU_PROMPTS.get(action)
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
