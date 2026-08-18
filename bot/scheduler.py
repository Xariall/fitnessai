"""Background scheduler for daily check-ins (UC-X02).

Morning check-in: 06:00 UTC — remind to log weight + breakfast.
Evening summary:  17:00 UTC — show daily nutrition/workout recap.

Каждый чек-ин трекает своё последнее сообщение (отдельно от навигационного
last_bot_msg_id из bot/helpers.py) и перед отправкой новой карточки удаляет
предыдущую того же типа — иначе они копятся в чате день за днём.
"""
import asyncio
import contextlib
import logging
from datetime import date, datetime, timezone

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey

logger = logging.getLogger(__name__)

_MORNING_MSG_KEY = "morning_checkin_msg_id"
_EVENING_MSG_KEY = "evening_summary_msg_id"


def _state_for_user(bot, storage: BaseStorage, telegram_user_id: int) -> FSMContext:
    """FSMContext для проактивной рассылки — приватный чат, chat_id == user_id."""
    key = StorageKey(bot_id=bot.id, chat_id=telegram_user_id, user_id=telegram_user_id)
    return FSMContext(storage=storage, key=key)


async def _send_tracked(bot, state: FSMContext, chat_id: int, data_key: str, text: str, parse_mode) -> None:
    """Удалить предыдущее сообщение этого чек-ина (если есть) → отправить новое → запомнить id."""
    data = await state.get_data()
    old_id = data.get(data_key)
    if old_id:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, old_id)

    sent = await bot.send_message(chat_id, text, parse_mode=parse_mode)
    await state.update_data(**{data_key: sent.message_id})


async def _get_all_users() -> list[dict]:
    from db.client import fetch

    try:
        return await fetch("SELECT telegram_user_id, name FROM users")
    except Exception:
        logger.exception("Scheduler: failed to fetch users")
        return []


async def _send_morning_checkin(bot, storage: BaseStorage, users: list[dict]) -> None:
    from aiogram.enums import ParseMode

    for user in users:
        uid = user["telegram_user_id"]
        try:
            state = _state_for_user(bot, storage, uid)
            await _send_tracked(
                bot, state, uid, _MORNING_MSG_KEY,
                f"☀️ *Доброе утро, {user['name']}!*\n\n"
                "Начни день правильно:\n"
                "• 🥛 Стакан воды сразу после пробуждения\n"
                "• ⚖️ Запиши свой вес (натощак)\n"
                "• 🍳 Залогируй завтрак\n\n"
                "_Напиши что ешь — считаю КБЖУ мгновенно!_",
                ParseMode.MARKDOWN,
            )
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("Scheduler: could not send morning to %s", uid)


async def _send_evening_summary(bot, storage: BaseStorage, users: list[dict]) -> None:
    from aiogram.enums import ParseMode

    from db.client import fetch, fetchrow

    today = date.today().isoformat()

    for user in users:
        uid = user["telegram_user_id"]
        try:
            user_row = await fetchrow(
                "SELECT id FROM users WHERE telegram_user_id = $1", uid
            )
            if not user_row:
                continue

            food = await fetch(
                "SELECT calories FROM food_logs WHERE user_id = $1 AND logged_at >= $2",
                user_row["id"], f"{today}T00:00:00",
            )

            workouts = await fetch(
                "SELECT id FROM workout_logs WHERE user_id = $1 AND completed_at >= $2",
                user_row["id"], f"{today}T00:00:00",
            )

            if not food:
                msg = (
                    "🌙 *Как прошёл день?*\n\n"
                    "Сегодня ничего не записано.\n"
                    "_Расскажи что ел — быстро посчитаем!_"
                )
            else:
                total_cal = sum(r["calories"] for r in food)
                workout_str = f"Тренировок: *{len(workouts)}* 💪\n" if workouts else ""
                msg = (
                    f"🌙 *Итог дня*\n\n"
                    f"Калорий: *{total_cal} ккал*\n"
                    f"{workout_str}"
                    "_Напиши «итог дня» для полной сводки_"
                )

            state = _state_for_user(bot, storage, uid)
            await _send_tracked(bot, state, uid, _EVENING_MSG_KEY, msg, ParseMode.MARKDOWN)
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("Scheduler: could not send evening to %s", uid)


async def run_scheduler(bot, storage: BaseStorage) -> None:
    """Background loop: fires morning (06:00 UTC) and evening (17:00 UTC) check-ins.

    storage — то же FSM-хранилище, что и у Dispatcher (bot/main.py), чтобы
    проактивные чек-ины трекали свои message_id так же, как обычная навигация.
    """
    last_morning: date | None = None
    last_evening: date | None = None

    logger.info("Scheduler started (morning=06:00 UTC, evening=17:00 UTC)")

    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            if now.hour == 6 and now.minute < 2 and last_morning != today:
                last_morning = today
                users = await _get_all_users()
                if users:
                    logger.info("Scheduler: sending morning check-in to %d users", len(users))
                    await _send_morning_checkin(bot, storage, users)

            if now.hour == 17 and now.minute < 2 and last_evening != today:
                last_evening = today
                users = await _get_all_users()
                if users:
                    logger.info("Scheduler: sending evening summary to %d users", len(users))
                    await _send_evening_summary(bot, storage, users)

        except Exception:
            logger.exception("Scheduler error")

        await asyncio.sleep(60)
