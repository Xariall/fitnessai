from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🥗 Питание")],
            [KeyboardButton(text="📊 Прогресс"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="💪 Мотивация")],
        ],
        resize_keyboard=True,
    )


def workout_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мой план", callback_data="submenu:my_plan")],
            [InlineKeyboardButton(text="✅ Записать тренировку", callback_data="submenu:log_workout")],
            [InlineKeyboardButton(text="📈 История", callback_data="submenu:workout_history")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def nutrition_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мой план питания", callback_data="submenu:nutrition_plan")],
            [InlineKeyboardButton(text="🍽 Итог за сегодня", callback_data="submenu:today_summary")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def progress_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Записать замер", callback_data="submenu:log_measurement")],
            [InlineKeyboardButton(text="📈 Моя динамика", callback_data="submenu:my_dynamics")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def confirm_keyboard(confirm_data: str, cancel_data: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, сбросить", callback_data=confirm_data),
                InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_data),
            ]
        ]
    )


def goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Похудение", callback_data="goal:lose_weight")],
            [InlineKeyboardButton(text="💪 Набор массы", callback_data="goal:gain_muscle")],
            [InlineKeyboardButton(text="⚖️ Поддержание формы", callback_data="goal:maintain")],
        ]
    )


def activity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🛋 Малоподвижный (офис, почти без спорта)",
                callback_data="activity:sedentary",
            )],
            [InlineKeyboardButton(
                text="🚶 Умеренный (1–3 тренировки в неделю)",
                callback_data="activity:light",
            )],
            [InlineKeyboardButton(
                text="🏃 Активный (4–5 тренировок в неделю)",
                callback_data="activity:moderate",
            )],
            [InlineKeyboardButton(
                text="🔥 Очень активный (ежедневные тренировки)",
                callback_data="activity:very_active",
            )],
        ]
    )


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поехали! 🎯", callback_data="onboarding:start")]
        ]
    )


def after_onboarding_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏋️ План тренировок", callback_data="submenu:my_plan"),
                InlineKeyboardButton(text="🥗 План питания", callback_data="submenu:nutrition_plan"),
            ],
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
