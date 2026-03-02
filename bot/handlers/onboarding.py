"""FSM-роутер онбординга: пошаговая анкета пользователя."""

import logging

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import Onboarding
from bot.keyboards import get_gender_kb, get_activity_kb, get_goal_kb
from bot.database.db import db

logger = logging.getLogger(__name__)

router = Router()

# Маппинг кнопок → значения для БД
GENDER_MAP = {"Мужчина": "male", "Женщина": "female"}
ACTIVITY_MAP = {
    "Сидячий": "sedentary",
    "Малоактивный": "moderate",
    "Активный": "active",
    "Атлет": "athlete",
}
GOAL_MAP = {
    "Похудение": "lose",
    "Поддержание": "maintain",
    "Набор массы": "gain",
    "Рекомпозиция": "recomposition",
}


# ── /cancel — прерывание анкеты ──────────────────────────────────────
@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    """Позволяет прервать анкету в любой момент."""
    current_state = await state.get_state()
    if current_state is None:
        return await message.answer("Нечего отменять — анкета не запущена.")

    await state.clear()
    await message.answer(
        "❌ Анкетирование прервано.\nЧтобы начать заново, нажми /profile",
        reply_markup=types.ReplyKeyboardRemove(),
    )


# ── Шаг 0: старт анкеты ─────────────────────────────────────────────
@router.message(Command("profile"))
async def start_onboarding(message: types.Message, state: FSMContext):
    """Начало анкеты по команде /profile."""
    await message.answer(
        "📋 Давай настроим твой профиль!\n\n"
        "Для начала, сколько тебе лет? (введи число)\n\n"
        "💡 Ты можешь прервать анкету в любой момент командой /cancel",
    )
    await state.set_state(Onboarding.waiting_for_age)


# ── Шаг 1: Возраст ──────────────────────────────────────────────────
@router.message(Onboarding.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    """Обработка возраста → запрос роста."""
    if not message.text.isdigit() or not (10 <= int(message.text) <= 100):
        return await message.answer(
            "⚠️ Введи корректный возраст цифрами (от 10 до 100), например: 25"
        )

    await state.update_data(age=int(message.text))
    await message.answer("Отлично! Какой у тебя рост в сантиметрах? (например, 175)")
    await state.set_state(Onboarding.waiting_for_height)


# ── Шаг 2: Рост ─────────────────────────────────────────────────────
@router.message(Onboarding.waiting_for_height)
async def process_height(message: types.Message, state: FSMContext):
    """Обработка роста → запрос веса."""
    try:
        height = float(message.text.replace(",", "."))
        if not (100 <= height <= 250):
            raise ValueError
    except ValueError:
        return await message.answer(
            "⚠️ Введи рост цифрами (от 100 до 250 см), например: 175"
        )

    await state.update_data(height=height)
    await message.answer("Записал. Какой у тебя текущий вес в килограммах? (например, 70)")
    await state.set_state(Onboarding.waiting_for_weight)


# ── Шаг 3: Вес ──────────────────────────────────────────────────────
@router.message(Onboarding.waiting_for_weight)
async def process_weight(message: types.Message, state: FSMContext):
    """Обработка веса → запрос пола."""
    try:
        weight = float(message.text.replace(",", "."))
        if not (30 <= weight <= 300):
            raise ValueError
    except ValueError:
        return await message.answer(
            "⚠️ Введи вес цифрами (от 30 до 300 кг), например: 70"
        )

    await state.update_data(weight=weight)
    await message.answer("Укажи свой пол:", reply_markup=get_gender_kb())
    await state.set_state(Onboarding.waiting_for_gender)


# ── Шаг 4: Пол ──────────────────────────────────────────────────────
@router.message(Onboarding.waiting_for_gender, F.text.in_(GENDER_MAP.keys()))
async def process_gender(message: types.Message, state: FSMContext):
    """Обработка пола → запрос уровня активности."""
    await state.update_data(gender=GENDER_MAP[message.text])
    await message.answer(
        "Какой у тебя уровень физической активности?",
        reply_markup=get_activity_kb(),
    )
    await state.set_state(Onboarding.waiting_for_activity)


@router.message(Onboarding.waiting_for_gender)
async def process_gender_invalid(message: types.Message):
    """Если пол введён вручную — просим выбрать кнопкой."""
    await message.answer(
        "⚠️ Пожалуйста, выбери один из вариантов на клавиатуре:",
        reply_markup=get_gender_kb(),
    )


# ── Шаг 5: Активность ───────────────────────────────────────────────
@router.message(Onboarding.waiting_for_activity, F.text.in_(ACTIVITY_MAP.keys()))
async def process_activity(message: types.Message, state: FSMContext):
    """Обработка активности → запрос цели."""
    await state.update_data(activity_level=ACTIVITY_MAP[message.text])
    await message.answer("Какая у тебя цель?", reply_markup=get_goal_kb())
    await state.set_state(Onboarding.waiting_for_goal)


@router.message(Onboarding.waiting_for_activity)
async def process_activity_invalid(message: types.Message):
    """Если активность введена вручную."""
    await message.answer(
        "⚠️ Выбери один из вариантов на клавиатуре:",
        reply_markup=get_activity_kb(),
    )


# ── Шаг 6: Цель (финальный) ─────────────────────────────────────────
@router.message(Onboarding.waiting_for_goal, F.text.in_(GOAL_MAP.keys()))
async def process_goal(message: types.Message, state: FSMContext):
    """Финальный шаг: сохранение профиля в БД."""
    await state.update_data(goal=GOAL_MAP[message.text])
    user_data = await state.get_data()

    # Формируем payload для БД
    db_payload = {
        "telegram_id": message.from_user.id,
        "username": message.from_user.username,
        "full_name": message.from_user.full_name,
        "age": user_data["age"],
        "gender": user_data["gender"],
        "height": user_data["height"],
        "activity_level": user_data["activity_level"],
        "goal": user_data["goal"],
        "medical_restrictions": None,
    }

    # Сохраняем в PostgreSQL
    await db.upsert_user(db_payload)
    await db.log_weight(message.from_user.id, user_data["weight"])

    logger.info(
        f"✅ Профиль сохранён: user={message.from_user.id}, "
        f"age={user_data['age']}, height={user_data['height']}, "
        f"weight={user_data['weight']}, goal={user_data['goal']}"
    )

    # Обратный маппинг для красивого вывода
    gender_display = {v: k for k, v in GENDER_MAP.items()}
    activity_display = {v: k for k, v in ACTIVITY_MAP.items()}

    await message.answer(
        f"🎉 <b>Профиль успешно создан!</b>\n\n"
        f"📊 Твои данные:\n"
        f"• Возраст: {user_data['age']}\n"
        f"• Рост: {user_data['height']} см\n"
        f"• Вес: {user_data['weight']} кг\n"
        f"• Пол: {gender_display.get(user_data['gender'], user_data['gender'])}\n"
        f"• Активность: {activity_display.get(user_data['activity_level'], user_data['activity_level'])}\n"
        f"• Цель: {message.text}\n\n"
        f"Теперь я могу рассчитать твою норму калорий! 💪",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.clear()


@router.message(Onboarding.waiting_for_goal)
async def process_goal_invalid(message: types.Message):
    """Если цель введена вручную."""
    await message.answer(
        "⚠️ Выбери один из вариантов на клавиатуре:",
        reply_markup=get_goal_kb(),
    )
