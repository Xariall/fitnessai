"""Shared bot helpers — no LLM, direct DB reads."""
import logging

from aiogram.types import InlineKeyboardMarkup

from db.client import get_client

logger = logging.getLogger(__name__)


async def has_active_cycle(telegram_user_id: int) -> bool:
    """Return True if the user has an active training cycle."""
    client = await get_client()
    rows = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .limit(1)
        .execute()
    ).data
    if not rows:
        return False
    user_id = rows[0]["id"]
    cycles = (
        await client.table("training_cycles")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    ).data
    return bool(cycles)


async def build_workout_keyboard(telegram_user_id: int) -> InlineKeyboardMarkup:
    """Return workout submenu keyboard — with 'Создать программу' if no active cycle."""
    from bot.keyboards.main import workout_submenu_keyboard, workout_submenu_keyboard_with_create
    if await has_active_cycle(telegram_user_id):
        return workout_submenu_keyboard()
    return workout_submenu_keyboard_with_create()


async def get_workout_section(telegram_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Возвращает (заголовок секции с баннером цикла, клавиатура). 2 запроса к БД."""
    from bot.keyboards.main import workout_submenu_keyboard, workout_submenu_keyboard_with_create

    client = await get_client()
    user_rows = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .limit(1)
        .execute()
    ).data
    if not user_rows:
        return (
            "🏋️ *Тренировки*\n\n_Создайте программу, чтобы видеть прогресс по циклу._",
            workout_submenu_keyboard_with_create(),
        )

    user_id = user_rows[0]["id"]
    cycle_rows = (
        await client.table("training_cycles")
        .select(
            "id,title,current_week,total_weeks,current_session_index,"
            "sessions_per_week,schedule,total_sessions_done"
        )
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not cycle_rows:
        return (
            "🏋️ *Тренировки*\n\n_Создайте программу, чтобы видеть прогресс по циклу._",
            workout_submenu_keyboard_with_create(),
        )

    c = cycle_rows[0]
    try:
        session = c["schedule"]["weeks"][c["current_week"] - 1]["sessions"][
            c["current_session_index"]
        ]
        total = c["total_weeks"] * c["sessions_per_week"]
        pct = int(c["total_sessions_done"] / total * 100) if total else 0
        banner = (
            f"📅 *{c['title']}* · Неделя {c['current_week']} из {c['total_weeks']} ({pct}%)\n"
            f"Следующая: {session['label']}"
        )
        return f"🏋️ *Тренировки*\n\n{banner}", workout_submenu_keyboard()
    except (IndexError, KeyError, TypeError) as exc:
        logger.warning("get_workout_section: failed to parse schedule: %s", exc)
        return "🏋️ *Тренировки*", workout_submenu_keyboard()


async def get_cycle_banner(user_id: str) -> str | None:
    """Return a formatted active-cycle status banner, or None if no active cycle.

    Used in show_workout_history and get_next_session_plan to prepend cycle context.
    Logs a warning (with cycle_id) if the stored schedule JSON is malformed.
    """
    client = await get_client()
    rows = (
        await client.table("training_cycles")
        .select(
            "id,title,current_week,total_weeks,current_session_index,"
            "sessions_per_week,schedule,total_sessions_done"
        )
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not rows:
        return None

    c = rows[0]
    try:
        session = c["schedule"]["weeks"][c["current_week"] - 1]["sessions"][
            c["current_session_index"]
        ]
        total = c["total_weeks"] * c["sessions_per_week"]
        pct = int(c["total_sessions_done"] / total * 100) if total else 0
        return (
            f"📅 *{c['title']}* · Неделя {c['current_week']} из {c['total_weeks']} ({pct}%)\n"
            f"Следующая: {session['label']}\n\n"
        )
    except (IndexError, KeyError, TypeError) as exc:
        logger.warning(
            "get_cycle_banner: failed to parse schedule cycle_id=%s: %s",
            c.get("id"),
            exc,
        )
        return None
