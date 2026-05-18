import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import callbacks, chat, clear, start
from bot.middlewares.user import UserMiddleware
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(UserMiddleware())

    # Routers (порядок важен: команды до общего chat)
    dp.include_router(start.router)
    dp.include_router(clear.router)
    dp.include_router(callbacks.router)
    dp.include_router(chat.router)

    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
