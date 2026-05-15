import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

from db.client import get_client

logger = logging.getLogger(__name__)


async def _get_user_id(telegram_user_id: int) -> Optional[str]:
    client = await get_client()
    result = (
        await client.table("users")
        .select("id")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None


@tool
async def log_progress(
    telegram_user_id: int,
    weight_kg: float,
    notes: Optional[str] = None,
) -> str:
    """Записать замер веса. Возвращает подтверждение с динамикой относительно предыдущего замера."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return "Пользователь не найден."

    client = await get_client()

    # Получить предыдущий замер для сравнения
    prev_result = (
        await client.table("progress_logs")
        .select("weight_kg")
        .eq("user_id", user_id)
        .order("measured_at", desc=True)
        .limit(1)
        .execute()
    )
    prev_weight: Optional[float] = prev_result.data[0]["weight_kg"] if prev_result.data else None

    await client.table("progress_logs").insert(
        {
            "user_id": user_id,
            "weight_kg": weight_kg,
            "notes": notes,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    # Обновить вес в профиле
    await client.table("users").update({"weight_kg": weight_kg}).eq("telegram_user_id", telegram_user_id).execute()

    if prev_weight is not None:
        delta = round(weight_kg - prev_weight, 1)
        sign = "+" if delta > 0 else ""
        trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
        return f"Записано: {weight_kg} кг {trend} ({sign}{delta} кг с прошлого замера)"
    return f"Записано: {weight_kg} кг — первый замер!"


@tool
async def get_progress_summary(telegram_user_id: int, days: int = 30) -> dict:
    """Показать динамику прогресса за период.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        days: Количество дней для анализа (по умолчанию 30).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {}

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    client = await get_client()
    result = (
        await client.table("progress_logs")
        .select("weight_kg, notes, measured_at")
        .eq("user_id", user_id)
        .gte("measured_at", since)
        .order("measured_at")
        .execute()
    )
    logs = result.data or []

    if not logs:
        return {"message": f"Нет замеров за последние {days} дней.", "logs": []}

    start_weight = logs[0]["weight_kg"]
    current_weight = logs[-1]["weight_kg"]
    delta = round(current_weight - start_weight, 1)
    sign = "+" if delta > 0 else ""

    return {
        "start_weight": start_weight,
        "current_weight": current_weight,
        "delta": f"{sign}{delta} кг за {days} дней",
        "logs": logs,
    }
