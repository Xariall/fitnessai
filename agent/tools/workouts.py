import logging
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)


@tool
async def generate_workout_plan(
    telegram_user_id: int,
    focus: str,
    duration_minutes: int,
) -> dict:
    """Сгенерировать план тренировки на основе профиля пользователя.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        focus: Группа мышц или тип тренировки (cardio/strength/flexibility).
        duration_minutes: Длительность тренировки в минутах.
    """
    # TODO: реализовать генерацию плана через LLM и сохранить в workouts
    raise NotImplementedError


@tool
async def log_workout(
    telegram_user_id: int,
    notes: str,
    workout_id: Optional[str] = None,
) -> str:
    """Записать выполненную тренировку."""
    # TODO: реализовать сохранение в workout_logs
    raise NotImplementedError


@tool
async def get_workout_history(telegram_user_id: int, limit: int = 5) -> list[dict]:
    """Получить историю тренировок пользователя."""
    client = await get_client()
    user = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    if not user.data:
        return []

    result = (
        await client.table("workout_logs")
        .select("*")
        .eq("user_id", user.data["id"])
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@tool
async def find_exercises(muscle_group: str, equipment: Optional[str] = None) -> list[dict]:
    """Найти упражнения по группе мышц или типу.

    Args:
        muscle_group: Группа мышц или тип тренировки.
        equipment: Доступное оборудование (optional).
    """
    # TODO: реализовать поиск по встроенной базе упражнений
    raise NotImplementedError
