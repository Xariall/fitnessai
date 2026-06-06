"""
Handler for viewing personal training records via Telegram Web App.
"""
import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("records"))
async def cmd_records(message: types.Message) -> None:
    """
    Show personal training records dashboard.
    Opens Telegram Web App with personal records, weekly volume, and 12-week recap.
    """
    button = InlineKeyboardButton(
        text="📊 Мои рекорды",
        web_app=WebAppInfo(url=settings.web_app_url),
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])

    await message.answer(
        "📊 *Твои тренировочные рекорды*\n\n"
        "Открой дашборд и посмотри:\n"
        "• Прогрессия нагрузки по упражнениям\n"
        "• Недельный объём по группам мышц\n"
        "• Итоги за 12 недель\n",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
