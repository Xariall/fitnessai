import asyncio
import contextlib
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from agent.graph import clear_thread
from bot.keyboards.main import confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()

_CLEAR_LIMIT = 100
_DELETE_SEMAPHORE_LIMIT = 5


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    await message.answer(
        "⚠️ *Сбросить историю чата?*\nЭто действие нельзя отменить.",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard("clear:confirm"),
    )


@router.callback_query(F.data == "clear:confirm")
async def handle_clear_confirm(callback: CallbackQuery) -> None:
    # Answer FIRST — always, so the spinner never hangs even if something below fails
    await callback.answer("Очищаю...")

    # Remove keyboard from the confirmation message
    with contextlib.suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(reply_markup=None)

    # Clear agent memory for this user
    clear_thread(callback.from_user.id)
    logger.info("Cleared agent memory for user %s", callback.from_user.id)

    # Delete recent messages in this chat
    chat_id = callback.message.chat.id
    current_id = callback.message.message_id
    ids_to_delete = range(max(1, current_id - _CLEAR_LIMIT + 1), current_id + 1)

    semaphore = asyncio.Semaphore(_DELETE_SEMAPHORE_LIMIT)
    await asyncio.gather(
        *[_try_delete(callback.bot, chat_id, msg_id, semaphore) for msg_id in ids_to_delete]
    )


async def _try_delete(bot, chat_id: int, message_id: int, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_message(chat_id, message_id)
