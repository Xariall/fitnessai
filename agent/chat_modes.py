"""Режимы работы агента — меняют фокус системного промпта."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMode:
    key: str
    label: str
    emoji: str
    prompt_suffix: str


MODES: dict[str, ChatMode] = {
    "general": ChatMode(
        key="general",
        label="Общий",
        emoji="🤖",
        prompt_suffix="",
    ),
    "workout": ChatMode(
        key="workout",
        label="Тренировки",
        emoji="🏋️",
        prompt_suffix=(
            "## Текущий режим: ТРЕНИРОВКИ\n"
            "Фокусируйся на тренировках, упражнениях и физической активности. "
            "Предлагай программы тренировок, анализируй нагрузку, давай советы по восстановлению. "
            "При любой возможности предлагай записать тренировку."
        ),
    ),
    "nutrition": ChatMode(
        key="nutrition",
        label="Питание",
        emoji="🥗",
        prompt_suffix=(
            "## Текущий режим: ПИТАНИЕ\n"
            "Фокусируйся на питании, КБЖУ и планах питания. "
            "Помогай подбирать продукты, считать калории, составлять меню под цель. "
            "При любой возможности предлагай записать приём пищи."
        ),
    ),
    "progress": ChatMode(
        key="progress",
        label="Прогресс",
        emoji="📊",
        prompt_suffix=(
            "## Текущий режим: ПРОГРЕСС\n"
            "Фокусируйся на отслеживании прогресса, динамике веса и достижениях. "
            "Анализируй тренды, отмечай успехи, предлагай корректировки в плане. "
            "При любой возможности предлагай записать замер веса."
        ),
    ),
    "motivation": ChatMode(
        key="motivation",
        label="Мотивация",
        emoji="💪",
        prompt_suffix=(
            "## Текущий режим: МОТИВАЦИЯ\n"
            "Будь энергичным и вдохновляющим коучем. "
            "Акцентируй внимание на достижениях пользователя, поддерживай в трудные моменты, "
            "давай конкретные краткосрочные цели. Используй инструмент send_motivation чаще обычного."
        ),
    ),
}

# Хранит текущий режим для каждого пользователя (in-memory, сбрасывается при рестарте)
_user_modes: dict[int, str] = {}


def get_mode(user_id: int) -> ChatMode:
    return MODES.get(_user_modes.get(user_id, "general"), MODES["general"])


def set_mode(user_id: int, mode_key: str) -> None:
    if mode_key in MODES:
        _user_modes[user_id] = mode_key
