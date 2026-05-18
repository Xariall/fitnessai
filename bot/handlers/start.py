import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import activity_keyboard, goal_keyboard, main_menu_keyboard
from db.client import get_client

logger = logging.getLogger(__name__)
router = Router()

GOAL_LABELS = {
    "lose_weight": "🔥 Похудеть",
    "gain_muscle": "💪 Набрать массу",
    "maintain": "⚖️ Поддерживать форму",
}

ACTIVITY_LABELS = {
    "sedentary": "🛋 Сидячий образ жизни",
    "light": "🚶 Лёгкая активность",
    "moderate": "🏃 Умеренная активность",
    "active": "💪 Высокая активность",
    "very_active": "🔥 Очень высокая активность",
}


class OnboardingFSM(StatesGroup):
    name = State()
    age = State()
    weight = State()
    height = State()
    goal = State()
    activity_level = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    if is_registered:
        await message.answer(
            f"С возвращением! Чем могу помочь?",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "Привет! Я твой персональный фитнес-коуч *FitnessAI* 🏋️\n\n"
        "Давай познакомимся. Как тебя зовут?"
    )
    await state.set_state(OnboardingFSM.name)


@router.message(OnboardingFSM.name)
async def onboarding_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await message.answer("Отлично! Сколько тебе лет?")
    await state.set_state(OnboardingFSM.age)


@router.message(OnboardingFSM.age)
async def onboarding_age(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.isdigit():
        await message.answer("Пожалуйста, введи возраст числом.")
        return
    await state.update_data(age=int(message.text))
    await message.answer("Какой у тебя вес? (в кг)")
    await state.set_state(OnboardingFSM.weight)


@router.message(OnboardingFSM.weight)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Пожалуйста, введи вес числом, например: 75.5")
        return
    await state.update_data(weight_kg=weight)
    await message.answer("Какой у тебя рост? (в см)")
    await state.set_state(OnboardingFSM.height)


@router.message(OnboardingFSM.height)
async def onboarding_height(message: Message, state: FSMContext) -> None:
    try:
        height = float(message.text.replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Пожалуйста, введи рост числом, например: 175")
        return
    await state.update_data(height_cm=height)
    await message.answer("Какова твоя цель?", reply_markup=goal_keyboard())
    await state.set_state(OnboardingFSM.goal)


@router.message(OnboardingFSM.goal)
async def onboarding_goal_text_fallback(message: Message) -> None:
    """Подсказка если пользователь пишет текст вместо нажатия кнопки."""
    await message.answer("Выбери цель, нажав на одну из кнопок выше 👆")


@router.callback_query(OnboardingFSM.goal, F.data.startswith("goal:"))
async def onboarding_goal_callback(callback: CallbackQuery, state: FSMContext) -> None:
    goal = callback.data.split(":")[1]
    label = GOAL_LABELS.get(goal, goal)
    await state.update_data(goal=goal)
    await callback.message.edit_text(f"Цель: {label} ✅")
    await callback.message.answer("Уровень активности?", reply_markup=activity_keyboard())
    await state.set_state(OnboardingFSM.activity_level)
    await callback.answer()


@router.message(OnboardingFSM.activity_level)
async def onboarding_activity_text_fallback(message: Message) -> None:
    """Подсказка если пользователь пишет текст вместо нажатия кнопки."""
    await message.answer("Выбери уровень активности, нажав на одну из кнопок выше 👆")


@router.callback_query(OnboardingFSM.activity_level, F.data.startswith("activity:"))
async def onboarding_activity_callback(callback: CallbackQuery, state: FSMContext) -> None:
    activity = callback.data.split(":")[1]
    label = ACTIVITY_LABELS.get(activity, activity)
    data = await state.get_data()
    await state.clear()

    try:
        client = await get_client()
        await client.table("users").insert(
            {
                **data,
                "activity_level": activity,
                "telegram_user_id": callback.from_user.id,
            }
        ).execute()
    except Exception:
        logger.exception("Failed to save user profile for %s", callback.from_user.id)
        await callback.message.answer(
            "Не удалось сохранить профиль — проблема с базой данных. "
            "Попробуй ещё раз через /start."
        )
        await callback.answer()
        return

    await callback.message.edit_text(f"Активность: {label} ✅")
    await callback.message.answer(
        f"Отлично, *{data['name']}*! Профиль создан 🎉\n\n"
        "Теперь я готов помогать тебе достигать целей. Чем займёмся?",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
