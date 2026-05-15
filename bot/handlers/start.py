import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.keyboards.main import main_menu_keyboard
from db.client import get_client

logger = logging.getLogger(__name__)
router = Router()


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
        "Привет! Я твой персональный фитнес-коуч FitnessAI 🏋️\n\n"
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
    await message.answer(
        "Какова твоя цель?\n\n"
        "1 — Похудеть\n"
        "2 — Набрать мышечную массу\n"
        "3 — Поддерживать форму"
    )
    await state.set_state(OnboardingFSM.goal)


GOAL_MAP = {"1": "lose_weight", "2": "gain_muscle", "3": "maintain"}


@router.message(OnboardingFSM.goal)
async def onboarding_goal(message: Message, state: FSMContext) -> None:
    goal = GOAL_MAP.get(message.text or "")
    if not goal:
        await message.answer("Введи 1, 2 или 3.")
        return
    await state.update_data(goal=goal)
    await message.answer(
        "Уровень активности?\n\n"
        "1 — Сидячий образ жизни\n"
        "2 — Лёгкая активность\n"
        "3 — Умеренная активность\n"
        "4 — Высокая активность\n"
        "5 — Очень высокая активность"
    )
    await state.set_state(OnboardingFSM.activity_level)


ACTIVITY_MAP = {
    "1": "sedentary",
    "2": "light",
    "3": "moderate",
    "4": "active",
    "5": "very_active",
}


@router.message(OnboardingFSM.activity_level)
async def onboarding_activity(message: Message, state: FSMContext) -> None:
    activity = ACTIVITY_MAP.get(message.text or "")
    if not activity:
        await message.answer("Введи число от 1 до 5.")
        return

    data = await state.get_data()
    await state.clear()

    client = await get_client()
    await client.table("users").insert(
        {
            **data,
            "activity_level": activity,
            "telegram_user_id": message.from_user.id,
        }
    ).execute()

    await message.answer(
        f"Отлично, {data['name']}! Профиль создан 🎉\n\n"
        "Теперь я готов помогать тебе достигать целей. Чем займёмся?",
        reply_markup=main_menu_keyboard(),
    )
