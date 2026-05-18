import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from langchain_core.messages import RemoveMessage

from agent.graph import agent_graph

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Очищает историю диалога с агентом для текущего пользователя."""
    thread_config = {"configurable": {"thread_id": str(message.from_user.id)}}

    try:
        current = await agent_graph.aget_state(thread_config)
        messages = current.values.get("messages", []) if current.values else []

        if not messages:
            await message.answer("История диалога уже пуста.")
            return

        await agent_graph.aupdate_state(
            thread_config,
            {"messages": [RemoveMessage(id=m.id) for m in messages]},
        )
        logger.info("Cleared %d messages for user %s", len(messages), message.from_user.id)
    except Exception:
        logger.exception("Failed to clear history for user %s", message.from_user.id)
        await message.answer("Не удалось очистить историю. Попробуй ещё раз.")
        return

    await message.answer("История диалога очищена. Начинаем с чистого листа!")
