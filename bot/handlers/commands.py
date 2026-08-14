import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
from bot.keyboards.main import help_keyboard, main_menu_keyboard
from db.client import fetchrow

logger = logging.getLogger(__name__)
router = Router()

_GOAL_LABELS = {
    "lose_weight": "🔥 Похудение",
    "gain_muscle": "💪 Набор массы",
    "maintain": "⚖️ Поддержание формы",
}

_ACTIVITY_LABELS = {
    "sedentary": "🛋 Малоподвижный",
    "light": "🚶 Умеренный",
    "moderate": "🏃 Активный",
    "active": "💪 Высокая активность",
    "very_active": "🔥 Очень активный",
}


async def get_profile_text(telegram_user_id: int) -> str:
    """Формирует текст профиля пользователя. Без side-эффектов."""
    try:
        profile = await fetchrow(
            "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
        )
    except Exception:
        logger.exception("Failed to load profile for %s", telegram_user_id)
        return "Не удалось загрузить профиль. Попробуй ещё раз."

    if not profile:
        return "Профиль не найден. Начни с команды /start."

    goal = _GOAL_LABELS.get(profile.get("goal", ""), profile.get("goal", "—"))
    activity = _ACTIVITY_LABELS.get(profile.get("activity_level", ""), profile.get("activity_level", "—"))
    weight = profile.get("weight_kg")
    height = profile.get("height_cm")

    bmi_line = ""
    if weight and height:
        bmi = weight / (height / 100) ** 2
        bmi_line = f"\n📐 *ИМТ:* {bmi:.1f}"

    return (
        f"👤 *Профиль*\n\n"
        f"🏷 *Имя:* {profile.get('name', '—')}\n"
        f"🎂 *Возраст:* {profile.get('age', '—')} лет\n"
        f"⚖️ *Вес:* {weight or '—'} кг\n"
        f"📏 *Рост:* {height or '—'} см"
        f"{bmi_line}\n\n"
        f"🎯 *Цель:* {goal}\n"
        f"🏃 *Активность:* {activity}\n\n"
        "_Чтобы обновить профиль, напиши мне, например: «мой вес теперь 80 кг»_"
    )


async def _show_profile(message: Message, telegram_user_id: int | None = None) -> None:
    uid = telegram_user_id or message.from_user.id
    text = await get_profile_text(uid)
    try:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer(text)


async def _quick_agent(message: Message, prompt: str) -> None:
    telegram_user_id = message.from_user.id
    try:
        result = await agent_graph.ainvoke(
            {
                "messages": [HumanMessage(content=prompt)],
                "user_profile": {},
                "telegram_user_id": telegram_user_id,
            },
            config={"configurable": {"thread_id": str(telegram_user_id)}},
        )
        reply = result["messages"][-1].content
    except Exception:
        logger.exception("Agent error for /command user %s", telegram_user_id)
        reply = "Произошла ошибка. Попробуй ещё раз."

    try:
        await message.answer(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer(reply)


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
        "🎙 Понимаю голосовые сообщения\n"
        "📷 Распознаю еду по фото\n\n"
        "*Просто напиши мне:*\n"
        "• «Что мне сегодня поесть?»\n"
        "• «Составь тренировку на ноги»\n"
        "• «Съел овсянку 200г»\n"
        "• «Вешу 85кг»\n"
        "• «Покажи мой прогресс»\n"
        "• Отправь фото блюда — запишу КБЖУ\n\n"
        "*Команды:*\n"
        "/stats — моя статистика\n"
        "/plan — план тренировки на сегодня\n"
        "/nutrition — план питания на день\n"
        "/today — итог питания за сегодня\n"
        "/progress — моя динамика веса\n"
        "/profile — мой профиль\n"
        "/menu — главное меню\n"
        "/clear — сбросить историю диалога\n\n"
        "💬 Что-то не работает? Пиши в поддержку — @fitnessai\\_support"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=help_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.helpers import send_and_track
    text = await get_profile_text(message.from_user.id)
    await send_and_track(message, text, state)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню", reply_markup=main_menu_keyboard())


@router.message(Command("plan"))
async def cmd_plan(message: Message, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    await _quick_agent(message, "Составь мне тренировку на сегодня")


@router.message(Command("nutrition"))
async def cmd_nutrition(message: Message, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    await _quick_agent(message, "Составь план питания на день")


@router.message(Command("today"))
async def cmd_today(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.handlers.direct import show_today_summary
    await show_today_summary(message, message.from_user.id, state)


@router.message(Command("progress"))
async def cmd_progress(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.handlers.direct import show_progress_dynamics
    await show_progress_dynamics(message, message.from_user.id, state)


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.handlers.direct import show_stats
    await show_stats(message, message.from_user.id, state)
