from typing import Optional

from db.client import get_client


async def get_user_id(telegram_user_id: int) -> Optional[str]:
    """Return internal UUID for a Telegram user, or None if not found."""
    client = await get_client()
    result = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None
