"""Обработчик /settings — выбор режима работы агента."""
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from agent.chat_modes import MODES, get_mode, set_mode

router = Router()


def _modes_keyboard(current_key: str) -> InlineKeyboardMarkup:
    buttons = []
    for key, mode in MODES.items():
        check = "✓ " if key == current_key else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{check}{mode.emoji} {mode.label}",
                callback_data=f"mode:{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("settings"))
async def cmd_settings(message: Message, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    current = get_mode(message.from_user.id)
    await message.answer(
        f"⚙️ *Настройки*\n\n"
        f"Текущий режим: {current.emoji} *{current.label}*\n\n"
        "Выбери режим — агент будет фокусироваться на выбранной теме:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_modes_keyboard(current.key),
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_select(callback: CallbackQuery) -> None:
    mode_key = callback.data.split(":", 1)[1]
    set_mode(callback.from_user.id, mode_key)
    mode = get_mode(callback.from_user.id)

    descriptions = {
        "general": "буду помогать со всем сразу.",
        "workout": "буду фокусироваться на тренировках и физической активности.",
        "nutrition": "буду фокусироваться на питании и КБЖУ.",
        "progress": "буду фокусироваться на твоём прогрессе и достижениях.",
        "motivation": "буду вдохновлять и поддерживать тебя.",
    }
    desc = descriptions.get(mode_key, "")

    await callback.message.edit_text(
        f"✅ Режим *{mode.emoji} {mode.label}* активирован\n\n"
        f"_Теперь я {desc}_",
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()
