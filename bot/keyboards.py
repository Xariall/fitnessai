"""Reply-клавиатуры для шагов анкеты с фиксированным выбором."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_gender_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужчина"), KeyboardButton(text="Женщина")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_activity_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сидячий"), KeyboardButton(text="Малоактивный")],
            [KeyboardButton(text="Активный"), KeyboardButton(text="Атлет")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_goal_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание")],
            [KeyboardButton(text="Набор массы"), KeyboardButton(text="Рекомпозиция")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
