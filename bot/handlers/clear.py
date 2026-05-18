import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()

# Сколько последних сообщений пытаемся удалить
_CLEAR_LIMIT = 100


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Удаляет последние сообщения в чате (до _CLEAR_LIMIT штук включая саму команду)."""
    chat_id = message.chat.id
    current_id = message.message_id

    # ID сообщений идут последовательно — берём диапазон до текущего включительно
    ids_to_delete = list(range(max(1, current_id - _CLEAR_LIMIT + 1), current_id + 1))

    # delete_messages молча пропускает те, что нельзя удалить (чужие/старые/уже удалённые)
    try:
        await message.bot.delete_messages(chat_id, ids_to_delete)
    except Exception:
        logger.exception("Failed to delete messages in chat %s", chat_id)
