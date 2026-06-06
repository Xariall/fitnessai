"""
Handler for viewing personal training records via Telegram Web App.
"""
import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("records"))
async def cmd_records(message: types.Message) -> None:
    """
    Show personal training records dashboard.
    Opens Telegram Web App with max lifts, weekly volume, and 12-week recap.
    """
    web_app_url = "https://fitnessai-webapp.vercel.app/records"

    button = InlineKeyboardButton(
        text="📊 View My Records",
        web_app=WebAppInfo(url=web_app_url),
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])

    await message.answer(
        "💪 *Your Training Records*\n\n"
        "View your personal records in an interactive dashboard:\n"
        "✓ Max lifts per exercise\n"
        "✓ Weekly volume progression by muscle group\n"
        "✓ 12-week recap with deltas\n",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
