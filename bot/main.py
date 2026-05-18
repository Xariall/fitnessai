import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import callbacks, chat, clear, commands, direct, start
from bot.middlewares.user import UserMiddleware
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_BOT_COMMANDS = [
    BotCommand(command="start", description="Начать / Главное меню"),
    BotCommand(command="plan", description="План тренировки на сегодня"),
    BotCommand(command="nutrition", description="План питания на день"),
    BotCommand(command="today", description="Итог питания за сегодня"),
    BotCommand(command="progress", description="Динамика веса"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="clear", description="Сбросить историю диалога"),
]


async def main() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(UserMiddleware())

    # Routers (порядок важен: специфичные до общего chat)
    dp.include_router(start.router)
    dp.include_router(clear.router)
    dp.include_router(commands.router)
    dp.include_router(direct.router)
    dp.include_router(callbacks.router)
    dp.include_router(chat.router)

    await bot.set_my_commands(_BOT_COMMANDS)

    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
