import asyncio
import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()

_CLEAR_LIMIT = 100


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Удаляет последние сообщения в чате (до _CLEAR_LIMIT штук включая саму команду)."""
    chat_id = message.chat.id
    current_id = message.message_id

    ids_to_delete = range(max(1, current_id - _CLEAR_LIMIT + 1), current_id + 1)

    await asyncio.gather(
        *[_try_delete(message.bot, chat_id, msg_id) for msg_id in ids_to_delete]
    )


async def _try_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass  # нельзя удалить: старше 48ч, уже удалено, нет прав — молча пропускаем
