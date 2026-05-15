import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)


@tool
async def log_progress(
    telegram_user_id: int,
    weight_kg: float,
    notes: Optional[str] = None,
) -> str:
    """Записать замер веса. Возвращает подтверждение с динамикой."""
    # TODO: реализовать сохранение в progress_logs и сравнение с предыдущим замером
    raise NotImplementedError


@tool
async def get_progress_summary(telegram_user_id: int, days: int = 30) -> dict:
    """Показать динамику прогресса за период.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        days: Количество дней для анализа (default 30).
    """
    # TODO: реализовать запрос progress_logs за период
    raise NotImplementedError
