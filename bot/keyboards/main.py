from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🥗 Питание")],
            [KeyboardButton(text="📊 Прогресс"), KeyboardButton(text="💪 Мотивация")],
        ],
        resize_keyboard=True,
    )


def goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔥 Похудеть", callback_data="goal:lose_weight"),
                InlineKeyboardButton(text="💪 Набрать массу", callback_data="goal:gain_muscle"),
            ],
            [InlineKeyboardButton(text="⚖️ Поддерживать форму", callback_data="goal:maintain")],
        ]
    )


def activity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛋 Сидячий", callback_data="activity:sedentary"),
                InlineKeyboardButton(text="🚶 Лёгкая", callback_data="activity:light"),
            ],
            [
                InlineKeyboardButton(text="🏃 Умеренная", callback_data="activity:moderate"),
                InlineKeyboardButton(text="💪 Высокая", callback_data="activity:active"),
            ],
            [InlineKeyboardButton(text="🔥 Очень высокая", callback_data="activity:very_active")],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🥗 План питания", callback_data="quick:nutrition_plan"),
                InlineKeyboardButton(text="🏋️ Тренировка", callback_data="quick:workout_plan"),
            ],
            [
                InlineKeyboardButton(text="📊 Мой прогресс", callback_data="quick:progress"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="quick:profile"),
            ],
        ]
    )


def onboarding_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="skip")]
        ]
    )
