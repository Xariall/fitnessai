"""Shared bot helpers — no LLM, direct DB reads."""
import contextlib
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)

from db.client import get_client

logger = logging.getLogger(__name__)


# ── Навигация: single-message pattern ────────────────────────────────────────


async def delete_tracked(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    *,
    also_user_msg: Message | None = None,
) -> None:
    """Удалить предыдущее отслеживаемое сообщение бота (и опционально сообщение юзера)."""
    data = await state.get_data()
    old_id = data.get("last_bot_msg_id")
    if old_id:
        await state.update_data(last_bot_msg_id=None)  # race protection: затираем до delete
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, old_id)
    if also_user_msg:
        with contextlib.suppress(Exception):
            await also_user_msg.delete()


async def send_and_track(
    target: Message | CallbackQuery,
    text: str,
    state: FSMContext,
    *,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    parse_mode: str | None = ParseMode.MARKDOWN,
    delete_user_msg: bool = False,
    silent: bool = False,
    allow_edit: bool = False,
) -> Message:
    """Удалить старую карточку → отправить новую → сохранить msg_id в стейт.

    silent      — disable_notification (карточка не звенит).
    allow_edit  — если target это CallbackQuery и last_bot_msg_id совпадает с
                  callback.message, использовать edit_text (без мерцания).
    """
    if isinstance(target, CallbackQuery):
        chat_id = target.message.chat.id
        bot = target.bot
        user_msg = None

        # edit path: back-кнопки — мгновенный переход без мерцания
        if allow_edit:
            data = await state.get_data()
            if data.get("last_bot_msg_id") == target.message.message_id:
                try:
                    await target.message.edit_text(
                        text, parse_mode=parse_mode, reply_markup=reply_markup,
                    )
                except TelegramBadRequest:
                    try:
                        await target.message.edit_text(text, reply_markup=reply_markup)
                    except TelegramBadRequest:
                        pass
                return target.message
    else:
        chat_id = target.chat.id
        bot = target.bot
        user_msg = target if delete_user_msg else None

    await delete_tracked(bot, chat_id, state, also_user_msg=user_msg)

    try:
        sent = await bot.send_message(
            chat_id, text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_notification=silent,
        )
    except TelegramBadRequest:
        sent = await bot.send_message(
            chat_id, text,
            reply_markup=reply_markup,
            disable_notification=silent,
        )
    await state.update_data(last_bot_msg_id=sent.message_id)
    return sent


async def attach_keyboard(
    target: Message | CallbackQuery,
    state: FSMContext,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Прикрепить клавиатуру к последнему отслеживаемому сообщению бота (edit_reply_markup).

    Используй вместо send_and_track когда сообщение агента должно ОСТАТЬСЯ видимым,
    а кнопка лишь добавляется к нему (например, «📋 По программе» после создания программы).
    Если редактирование не удалось — ничего не делаем (кнопка просто не появится).
    """
    if isinstance(target, CallbackQuery):
        bot = target.bot
        chat_id = target.message.chat.id
    else:
        bot = target.bot
        chat_id = target.chat.id

    data = await state.get_data()
    msg_id = data.get("last_bot_msg_id")
    if not msg_id:
        return
    with contextlib.suppress(Exception):
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=reply_markup,
        )


async def clear_fsm_keep_nav(state: FSMContext) -> None:
    """Очистить FSM state, но сохранить навигационный last_bot_msg_id."""
    data = await state.get_data()
    nav_msg_id = data.get("last_bot_msg_id")
    await state.clear()
    if nav_msg_id:
        await state.update_data(last_bot_msg_id=nav_msg_id)


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
