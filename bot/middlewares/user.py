import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from db.client import fetchrow

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """Проверяет регистрацию пользователя перед каждым сообщением.
    Если пользователь не зарегистрирован — редиректит на онбординг.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        telegram_user_id = event.from_user.id
        row = await fetchrow(
            "SELECT id FROM users WHERE telegram_user_id = $1", telegram_user_id
        )

        data["is_registered"] = bool(row)
        return await handler(event, data)
