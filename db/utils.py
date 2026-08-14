from typing import Optional

from db.client import fetchrow


async def get_user_id(telegram_user_id: int) -> Optional[str]:
    """Return internal UUID for a Telegram user, or None if not found."""
    row = await fetchrow(
        "SELECT id FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    return row["id"] if row else None
