import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import callbacks, chat, clear, commands, direct, photo, start, records
from bot.handlers import inline as inline_handler
from bot.handlers import settings as settings_handler
from bot.middlewares.user import UserMiddleware
from bot.scheduler import run_scheduler
from config import settings

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Заглушаем шумные библиотеки
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("h2").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_BOT_COMMANDS = [
    BotCommand(command="start", description="Начать / Главное меню"),
    BotCommand(command="stats", description="Моя статистика"),
    BotCommand(command="plan", description="План тренировки на сегодня"),
    BotCommand(command="nutrition", description="План питания на день"),
    BotCommand(command="today", description="Итог питания за сегодня"),
    BotCommand(command="progress", description="Динамика веса"),
    BotCommand(command="records", description="Мои рекорды"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="settings", description="Настройки режима агента"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="clear", description="Сбросить историю диалога"),
]


async def main() -> None:
    from agent.graph import cleanup_graph, init_graph

    # Инициализируем граф с персистентным checkpointer-ом (SQLite)
    await init_graph()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(UserMiddleware())

    # Routers (порядок важен: специфичные до общего chat)
    dp.include_router(start.router)
    dp.include_router(clear.router)
    dp.include_router(settings_handler.router)  # /settings + mode:* callbacks
    dp.include_router(commands.router)
    dp.include_router(records.router)  # /records command
    dp.include_router(direct.router)
    dp.include_router(callbacks.router)
    dp.include_router(photo.router)       # до chat.router — photo перехватывает F.photo
    dp.include_router(chat.router)
    dp.include_router(inline_handler.router)  # inline queries

    await bot.set_my_commands(_BOT_COMMANDS)

    logger.info("Starting bot (persistent memory: MemorySaver + pickle)...")
    scheduler_task = asyncio.create_task(run_scheduler(bot, dp.storage))
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "inline_query"],
            drop_pending_updates=True,
        )
    finally:
        scheduler_task.cancel()
        await cleanup_graph()


if __name__ == "__main__":
    asyncio.run(main())
