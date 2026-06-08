import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import (
    activity_keyboard,
    after_onboarding_keyboard,
    goal_keyboard,
    main_menu_keyboard,
    no_injuries_keyboard,
    start_keyboard,
)
from agent.constants import ACTIVITY_MULTIPLIERS as _ACTIVITY_MULTIPLIERS, GOAL_ADJUSTMENTS as _GOAL_ADJUSTMENTS
from db.client import get_client

logger = logging.getLogger(__name__)
router = Router()

GOAL_LABELS = {
    "lose_weight": "🔥 Похудение",
    "gain_muscle": "💪 Набор массы",
    "maintain": "⚖️ Поддержание формы",
}

ACTIVITY_LABELS = {
    "sedentary": "🛋 Малоподвижный образ жизни",
    "light": "🚶 Умеренный (1–3 тренировки/нед)",
    "moderate": "🏃 Активный (4–5 тренировок/нед)",
    "active": "💪 Высокая активность",
    "very_active": "🔥 Очень активный (ежедневно)",
}


def _calculate_norms(weight_kg: float, height_cm: float, age: int, activity: str, goal: str) -> dict:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    tdee = bmr * _ACTIVITY_MULTIPLIERS.get(activity, 1.55)
    calories = int(tdee + _GOAL_ADJUSTMENTS.get(goal, 0))
    protein = round(weight_kg * 2.0, 1)
    fat = round(calories * 0.25 / 9)
    carbs = round((calories - protein * 4 - fat * 9) / 4)
    return {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}


_INJURY_KEYWORDS: dict[str, list[str]] = {
    "knee_injury":      ["колен", "knee", "мениск", "связк"],
    "lower_back":       ["поясниц", "спин", "lower back", "back", "протрузи", "грыж", "позвоноч", "крестц", "сколиоз", "остеохондроз"],
    "shoulder_injury":  ["плеч", "shoulder", "ротатор"],
    "elbow":            ["локот", "локт", "elbow", "теннисн"],
    "wrist":            ["запясть", "wrist", "запяст"],
    "hip":              ["бедр", "таз", "hip", "тазобедр"],
    "neck":             ["шей", "шея", "neck", "шейн"],
}


def _parse_injuries(text: str) -> list[str]:
    text_lower = text.lower()
    matched = [
        tag
        for tag, keywords in _INJURY_KEYWORDS.items()
        if any(kw in text_lower for kw in keywords)
    ]
    # Всегда сохраняем оригинальный текст — чтобы агент видел
    # условия вроде «диабет», которые не попадают в структурированные теги
    result = matched[:]
    raw = text.strip()
    if raw not in result:
        result.append(raw)
    return result


def _step_header(step: int, total: int = 7) -> str:
    """Визуальный индикатор прогресса онбординга."""
    filled = round(step / total * 10)
    bar = "▓" * filled + "░" * (10 - filled)
    return f"{bar}  Шаг {step} из {total}\n\n"


class OnboardingFSM(StatesGroup):
    name = State()
    age = State()
    weight = State()
    height = State()
    goal = State()
    activity_level = State()
    injuries = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    await state.clear()
    if is_registered:
        await message.answer(
            f"С возвращением! Чем займёмся? 💪",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "Привет! Я FitnessAI — персональный AI-тренер в Telegram. 👋\n\n"
        "Составлю план тренировок и питания, посчитаю КБЖУ и буду отслеживать твой прогресс.\n\n"
        "Настройка займёт 2 минуты — давай начнём! 🚀",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "onboarding:start")
async def onboarding_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{_step_header(1)}Как тебя зовут?")
    await state.set_state(OnboardingFSM.name)
    await callback.answer()


@router.message(OnboardingFSM.name)
async def onboarding_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await message.answer(
        f"{_step_header(2)}Какая у тебя основная цель?",
        reply_markup=goal_keyboard(),
    )
    await state.set_state(OnboardingFSM.goal)


@router.message(OnboardingFSM.goal)
async def onboarding_goal_text_fallback(message: Message) -> None:
    await message.answer("Выбери цель, нажав на одну из кнопок выше 👆")


@router.callback_query(OnboardingFSM.goal, F.data.startswith("goal:"))
async def onboarding_goal_callback(callback: CallbackQuery, state: FSMContext) -> None:
    goal = callback.data.split(":")[1]
    label = GOAL_LABELS.get(goal, goal)
    await state.update_data(goal=goal)
    await callback.message.edit_text(f"Цель: {label} ✅")
    await callback.message.answer(
        f"{_step_header(3)}Как бы ты описал свою текущую активность?",
        reply_markup=activity_keyboard(),
    )
    await state.set_state(OnboardingFSM.activity_level)
    await callback.answer()


@router.message(OnboardingFSM.activity_level)
async def onboarding_activity_text_fallback(message: Message) -> None:
    await message.answer("Выбери уровень активности, нажав на одну из кнопок выше 👆")


@router.callback_query(OnboardingFSM.activity_level, F.data.startswith("activity:"))
async def onboarding_activity_callback(callback: CallbackQuery, state: FSMContext) -> None:
    activity = callback.data.split(":")[1]
    label = ACTIVITY_LABELS.get(activity, activity)
    await state.update_data(activity_level=activity)
    await callback.message.edit_text(f"Активность: {label} ✅")
    await callback.message.answer(f"{_step_header(4)}Сколько тебе лет?")
    await state.set_state(OnboardingFSM.age)
    await callback.answer()


@router.message(OnboardingFSM.age)
async def onboarding_age(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.isdigit():
        await message.answer("Пожалуйста, введи возраст числом, например: 28")
        return
    age = int(message.text)
    if not 10 <= age <= 120:
        await message.answer("Возраст должен быть от 10 до 120 лет. Попробуй снова:")
        return
    await state.update_data(age=age)
    await message.answer(f"{_step_header(5)}Какой у тебя рост? (в см, например: 178)")
    await state.set_state(OnboardingFSM.height)


@router.message(OnboardingFSM.height)
async def onboarding_height(message: Message, state: FSMContext) -> None:
    try:
        height = float(message.text.replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Пожалуйста, введи рост числом, например: 178")
        return
    if not 100 <= height <= 250:
        await message.answer("Рост должен быть от 100 до 250 см. Попробуй снова:")
        return
    await state.update_data(height_cm=height)
    await message.answer(f"{_step_header(6)}Какой сейчас вес? (в кг, например: 82.5)")
    await state.set_state(OnboardingFSM.weight)


@router.message(OnboardingFSM.weight)
async def onboarding_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Пожалуйста, введи вес числом, например: 82.5")
        return
    if not 30 <= weight <= 300:
        await message.answer("Вес должен быть от 30 до 300 кг. Попробуй снова:")
        return

    await state.update_data(weight_kg=weight)
    await state.set_state(OnboardingFSM.injuries)
    await message.answer(
        f"{_step_header(7)}Есть травмы или противопоказания? 🩺\n\n"
        "Напиши что беспокоит — например: «колено, поясница».\n"
        "Буду учитывать при генерации тренировок.\n\n"
        "_Если всё в порядке — нажми кнопку ниже:_",
        parse_mode="Markdown",
        reply_markup=no_injuries_keyboard(),
    )


async def _finish_onboarding(message: Message, state: FSMContext, injuries: list[str]) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        client = await get_client()
        await client.table("users").insert(
            {
                **data,
                "telegram_user_id": message.from_user.id,
                "injuries": injuries,
            }
        ).execute()
    except Exception:
        logger.exception("Failed to save user profile for %s", message.from_user.id)
        await message.answer(
            "Не удалось сохранить профиль — проблема с базой данных. "
            "Попробуй ещё раз через /start."
        )
        return

    norms = _calculate_norms(
        weight_kg=data.get("weight_kg", 70),
        height_cm=data.get("height_cm", 170),
        age=data.get("age", 25),
        activity=data.get("activity_level", "moderate"),
        goal=data.get("goal", "maintain"),
    )

    injuries_line = ""
    if injuries:
        _tag_labels = {
            "knee_injury": "колено",
            "lower_back": "поясница/спина",
            "shoulder_injury": "плечо",
            "elbow": "локоть",
            "wrist": "запястье",
            "hip": "бедро/таз",
            "neck": "шея",
        }
        readable = ", ".join(_tag_labels.get(i, i) for i in injuries)
        injuries_line = f"⚠️ Учту: {readable}\n\n"

    await message.answer(
        f"✅ Отлично, *{data['name']}*! Всё готово.\n\n"
        f"{injuries_line}"
        f"Твоя норма: *{norms['calories']} ккал/день*\n"
        f"Белки: {norms['protein']}г · Жиры: {norms['fat']}г · Углеводы: {norms['carbs']}г\n\n"
        "Хочешь сразу получить план тренировок или план питания?\n"
        "_Или просто напиши мне — я всегда здесь 💪_",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(OnboardingFSM.injuries, F.data == "onboarding:no_injuries")
async def onboarding_no_injuries(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _finish_onboarding(callback.message, state, injuries=[])


@router.message(OnboardingFSM.injuries)
async def onboarding_injuries(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Напиши что беспокоит или нажми «Нет травм ✅»")
        return
    injuries = _parse_injuries(text)
    await _finish_onboarding(message, state, injuries=injuries)
