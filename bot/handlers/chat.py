import logging

from aiogram import Router
from aiogram.types import Message
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def handle_message(message: Message, is_registered: bool = False) -> None:
    """Основной обработчик — передаёт сообщение агенту."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    telegram_user_id = message.from_user.id
    user_input = message.text or ""

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        result = await agent_graph.ainvoke(
            # Передаём только новое сообщение — checkpointer сам добавит его к истории треда
            {
                "messages": [HumanMessage(content=user_input)],
                "user_profile": {},
                "telegram_user_id": telegram_user_id,
            },
            config={"configurable": {"thread_id": str(telegram_user_id)}},
        )
        reply = result["messages"][-1].content
    except Exception:
        logger.exception("Agent error for user %s", telegram_user_id)
        reply = "Произошла ошибка при обработке запроса. Попробуй ещё раз."

    await message.answer(reply)
