import logging

from aiogram import Router
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query()
async def handle_callback(callback: CallbackQuery) -> None:
    """Заглушка для inline-кнопок."""
    await callback.answer()
