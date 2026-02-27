"""FitnessAI Bot — точка входа."""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers import router
from bot.database.db import Database

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Глобальный экземпляр БД
db = Database()


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        sys.exit(1)

    # Подключаемся к БД и создаём таблицы
    await db.connect()
    await db.init_tables()

    bot = Bot(token=token)
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(router)

    logger.info("🚀 Бот FitnessAi запускается...")

    try:
        # Удаляем вебхук (на случай если был) и запускаем polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        # Graceful shutdown
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
