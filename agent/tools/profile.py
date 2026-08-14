import logging
from typing import Any

from langchain_core.tools import tool

from db.client import fetchrow

logger = logging.getLogger(__name__)


@tool
async def get_user_profile(telegram_user_id: int) -> dict[str, Any]:
    """Получить профиль пользователя из БД по telegram_user_id."""
    row = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    return row or {}


@tool
async def update_user_profile(telegram_user_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Обновить поля профиля пользователя."""
    if not fields:
        return await get_user_profile.ainvoke({"telegram_user_id": telegram_user_id})

    columns = list(fields.keys())
    set_clause = ", ".join(f"{col} = ${i + 1}" for i, col in enumerate(columns))
    args = [fields[col] for col in columns]
    args.append(telegram_user_id)

    row = await fetchrow(
        f"UPDATE users SET {set_clause} WHERE telegram_user_id = ${len(args)} RETURNING *",
        *args,
    )
    return row or {}
