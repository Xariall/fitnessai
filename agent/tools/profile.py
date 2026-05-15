import logging
from typing import Any

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)


@tool
async def get_user_profile(telegram_user_id: int) -> dict[str, Any]:
    """Получить профиль пользователя из БД по telegram_user_id."""
    client = await get_client()
    result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return result.data or {}


@tool
async def update_user_profile(telegram_user_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Обновить поля профиля пользователя."""
    client = await get_client()
    result = (
        await client.table("users")
        .update(fields)
        .eq("telegram_user_id", telegram_user_id)
        .execute()
    )
    return result.data[0] if result.data else {}
