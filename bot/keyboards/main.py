from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


_BACK_LABELS: dict[str, str] = {
    "workout":   "◀️ К тренировкам",
    "nutrition": "◀️ К питанию",
    "progress":  "◀️ К прогрессу",
}


def _back_button(section: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=_BACK_LABELS[section],
        callback_data=f"back:{section}",
    )


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
            [
                InlineKeyboardButton(text="💪 Тренировка сегодня", callback_data="submenu:train_today"),
                InlineKeyboardButton(text="✅ Записать тренировку", callback_data="submenu:log_workout"),
            ],
            [
                InlineKeyboardButton(text="📅 Моя программа", callback_data="submenu:active_cycle"),
                InlineKeyboardButton(text="📈 История", callback_data="submenu:workout_history"),
            ],
            [
                InlineKeyboardButton(text="📊 Итог недели", callback_data="after:weekly"),
                InlineKeyboardButton(text="🔄 Восстановление", callback_data="after:recovery"),
            ],
        ]
    )


def cycle_complete_keyboard(cycle_id: str = "") -> InlineKeyboardMarkup:
    start_new_data = f"cycle:start_new:{cycle_id}" if cycle_id else "cycle:start_new"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Начать новый цикл", callback_data=start_new_data)],
            [InlineKeyboardButton(text="📊 Посмотреть итоги", callback_data="after:stats")],
        ]
    )


def nutrition_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мой план питания", callback_data="submenu:nutrition_plan")],
            [InlineKeyboardButton(text="🍽 Итог за сегодня", callback_data="submenu:today_summary")],
            [
                InlineKeyboardButton(text="➕ Добавить еду", callback_data="after:add_food"),
                InlineKeyboardButton(text="💧 Норма воды", callback_data="after:hydration"),
            ],
        ]
    )


def progress_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Записать замер", callback_data="submenu:log_measurement")],
            [InlineKeyboardButton(text="📈 Моя динамика", callback_data="submenu:my_dynamics")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="after:stats")],
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
                text="💪 Высокая активность (5–6 тренировок)",
                callback_data="activity:active",
            )],
            [InlineKeyboardButton(
                text="🔥 Очень активный (ежедневные тренировки)",
                callback_data="activity:very_active",
            )],
        ]
    )


def no_injuries_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Нет травм ✅", callback_data="onboarding:no_injuries")]
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
                InlineKeyboardButton(text="💪 Создать программу", callback_data="submenu:create_cycle"),
                InlineKeyboardButton(text="🥗 План питания", callback_data="submenu:nutrition_plan"),
            ],
        ]
    )


def no_active_cycle_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💪 Создать программу", callback_data="submenu:create_cycle")],
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


# ── Контекстные кнопки после прямых ответов ──────────────────────────────────

def after_nutrition_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить еду", callback_data="after:add_food"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="after:stats"),
            ],
            [_back_button("nutrition")],
        ]
    )


def after_workout_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Записать тренировку", callback_data="after:log_workout"),
                InlineKeyboardButton(text="💪 Тренировка сегодня", callback_data="submenu:train_today"),
            ],
            [_back_button("workout")],
        ]
    )


def after_progress_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Записать замер", callback_data="submenu:log_measurement"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="after:stats"),
            ],
            [_back_button("progress")],
        ]
    )


def after_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🍽 Питание", callback_data="submenu:today_summary"),
                InlineKeyboardButton(text="🏋️ Тренировка", callback_data="submenu:workout_history"),
            ],
            [
                InlineKeyboardButton(text="📈 Прогресс", callback_data="after:dynamics"),
                _back_button("progress"),
            ],
        ]
    )


def after_weight_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Моя динамика", callback_data="after:dynamics"),
                _back_button("progress"),
            ],
        ]
    )
