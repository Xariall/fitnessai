"""Background scheduler for daily check-ins (UC-X02).

Morning check-in: 06:00 UTC — remind to log weight + breakfast.
Evening summary:  17:00 UTC — show daily nutrition/workout recap.
"""
import asyncio
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


async def _get_all_users(client) -> list[dict]:
    try:
        result = await client.table("users").select("telegram_user_id, name").execute()
        return result.data or []
    except Exception:
        logger.exception("Scheduler: failed to fetch users")
        return []


async def _send_morning_checkin(bot, users: list[dict]) -> None:
    from aiogram.enums import ParseMode

    for user in users:
        try:
            await bot.send_message(
                user["telegram_user_id"],
                f"☀️ *Доброе утро, {user['name']}!*\n\n"
                "Начни день правильно:\n"
                "• 🥛 Стакан воды сразу после пробуждения\n"
                "• ⚖️ Запиши свой вес (натощак)\n"
                "• 🍳 Залогируй завтрак\n\n"
                "_Напиши что ешь — считаю КБЖУ мгновенно!_",
                parse_mode=ParseMode.MARKDOWN,
            )
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("Scheduler: could not send morning to %s", user["telegram_user_id"])


async def _send_evening_summary(bot, users: list[dict]) -> None:
    from aiogram.enums import ParseMode

    from db.client import get_client

    client = await get_client()
    today = date.today().isoformat()

    for user in users:
        uid = user["telegram_user_id"]
        try:
            user_row = (
                await client.table("users")
                .select("id")
                .eq("telegram_user_id", uid)
                .single()
                .execute()
            )
            if not user_row.data:
                continue

            food = (
                await client.table("food_logs")
                .select("calories")
                .eq("user_id", user_row.data["id"])
                .gte("logged_at", f"{today}T00:00:00")
                .execute()
            ).data or []

            workouts = (
                await client.table("workout_logs")
                .select("id")
                .eq("user_id", user_row.data["id"])
                .gte("completed_at", f"{today}T00:00:00")
                .execute()
            ).data or []

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

            await bot.send_message(uid, msg, parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("Scheduler: could not send evening to %s", uid)


async def run_scheduler(bot) -> None:
    """Background loop: fires morning (06:00 UTC) and evening (17:00 UTC) check-ins."""
    from db.client import get_client

    last_morning: date | None = None
    last_evening: date | None = None

    logger.info("Scheduler started (morning=06:00 UTC, evening=17:00 UTC)")

    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            if now.hour == 6 and now.minute < 2 and last_morning != today:
                last_morning = today
                client = await get_client()
                users = await _get_all_users(client)
                if users:
                    logger.info("Scheduler: sending morning check-in to %d users", len(users))
                    await _send_morning_checkin(bot, users)

            if now.hour == 17 and now.minute < 2 and last_evening != today:
                last_evening = today
                client = await get_client()
                users = await _get_all_users(client)
                if users:
                    logger.info("Scheduler: sending evening summary to %d users", len(users))
                    await _send_evening_summary(bot, users)

        except Exception:
            logger.exception("Scheduler error")

        await asyncio.sleep(60)
