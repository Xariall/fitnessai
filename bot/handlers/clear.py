import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()

_CLEAR_LIMIT = 100


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Показывает подтверждение перед сбросом истории диалога."""
    await message.answer(
        "⚠️ *Сбросить историю чата?*\nЭто действие нельзя отменить.",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard("clear:confirm"),
    )


_DELETE_SEMAPHORE_LIMIT = 5


@router.callback_query(F.data == "clear:confirm")
async def handle_clear_confirm(callback: CallbackQuery) -> None:
    """Удаляет последние сообщения в чате после подтверждения."""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Очищаю...")

    chat_id = callback.message.chat.id
    current_id = callback.message.message_id
    ids_to_delete = range(max(1, current_id - _CLEAR_LIMIT + 1), current_id + 1)

    semaphore = asyncio.Semaphore(_DELETE_SEMAPHORE_LIMIT)
    await asyncio.gather(
        *[_try_delete(callback.bot, chat_id, msg_id, semaphore) for msg_id in ids_to_delete]
    )


async def _try_delete(bot, chat_id: int, message_id: int, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramBadRequest:
            pass
