import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph

logger = logging.getLogger(__name__)
router = Router()

_QUICK_PROMPTS = {
    "nutrition_plan": "Составь мне план питания на сегодня",
    "workout_plan": "Составь мне тренировку на сегодня",
    "progress": "Покажи мой прогресс за последний месяц",
    "profile": "Покажи мой профиль",
}


@router.callback_query(F.data.startswith("quick:"))
async def handle_quick_action(callback: CallbackQuery) -> None:
    """Быстрые действия из /help меню."""
    action = callback.data.split(":")[1]
    prompt = _QUICK_PROMPTS.get(action)
    if not prompt:
        await callback.answer()
        return

    await callback.answer("⏳ Обрабатываю...")

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
        logger.exception("Agent error for quick action %s, user %s", action, telegram_user_id)
        reply = "Произошла ошибка. Попробуй ещё раз."

    try:
        await callback.message.answer(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.answer(reply)


@router.callback_query()
async def handle_callback_fallback(callback: CallbackQuery) -> None:
    """Заглушка для необработанных inline-кнопок."""
    await callback.answer()
