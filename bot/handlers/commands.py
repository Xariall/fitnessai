import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.main import help_keyboard, main_menu_keyboard
from db.client import get_client

logger = logging.getLogger(__name__)
router = Router()

_GOAL_LABELS = {
    "lose_weight": "🔥 Похудеть",
    "gain_muscle": "💪 Набрать массу",
    "maintain": "⚖️ Поддерживать форму",
}

_ACTIVITY_LABELS = {
    "sedentary": "🛋 Сидячий",
    "light": "🚶 Лёгкая",
    "moderate": "🏃 Умеренная",
    "active": "💪 Высокая",
    "very_active": "🔥 Очень высокая",
}


@router.message(Command("help"))
async def cmd_help(message: Message, is_registered: bool = False) -> None:
    text = (
        "🤖 *FitnessAI* — твой персональный AI-тренер\n\n"
        "*Что я умею:*\n"
        "🥗 Считаю калории и КБЖУ\n"
        "💪 Составляю планы тренировок\n"
        "📊 Отслеживаю прогресс\n"
        "⚖️ Записываю вес и статистику\n"
        "🎯 Помогаю достигать целей\n"
        "🎙 Понимаю голосовые сообщения\n\n"
        "*Просто напишите мне:*\n"
        "• «Что мне сегодня поесть?»\n"
        "• «Составь тренировку на ноги»\n"
        "• «Съел овсянку 200г»\n"
        "• «Вешу 85кг»\n"
        "• «Покажи мой прогресс»\n\n"
        "*Команды:*\n"
        "/help — это меню\n"
        "/profile — мой профиль\n"
        "/clear — сбросить историю диалога\n"
        "/menu — главное меню"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=help_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    try:
        client = await get_client()
        result = (
            await client.table("users")
            .select("*")
            .eq("telegram_user_id", message.from_user.id)
            .single()
            .execute()
        )
        profile = result.data
    except Exception:
        logger.exception("Failed to load profile for %s", message.from_user.id)
        await message.answer("Не удалось загрузить профиль. Попробуй ещё раз.")
        return

    if not profile:
        await message.answer("Профиль не найден. Начни с команды /start.")
        return

    goal = _GOAL_LABELS.get(profile.get("goal", ""), profile.get("goal", "—"))
    activity = _ACTIVITY_LABELS.get(profile.get("activity_level", ""), profile.get("activity_level", "—"))
    weight = profile.get("weight_kg")
    height = profile.get("height_cm")

    bmi_line = ""
    if weight and height:
        bmi = weight / (height / 100) ** 2
        bmi_line = f"\n📐 *ИМТ:* {bmi:.1f}"

    text = (
        f"👤 *Профиль*\n\n"
        f"🏷 *Имя:* {profile.get('name', '—')}\n"
        f"🎂 *Возраст:* {profile.get('age', '—')} лет\n"
        f"⚖️ *Вес:* {weight or '—'} кг\n"
        f"📏 *Рост:* {height or '—'} см"
        f"{bmi_line}\n\n"
        f"🎯 *Цель:* {goal}\n"
        f"🏃 *Активность:* {activity}\n\n"
        "_Чтобы обновить профиль, напиши мне, например: «мой вес теперь 80кг»_"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
