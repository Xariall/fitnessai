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
async def get_weekly_summary(telegram_user_id: int) -> dict:
    """Get a weekly overview: workouts done, avg nutrition vs norm, weight change.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    from datetime import date

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден."}

    client = await get_client()
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    workouts_result = (
        await client.table("workout_logs")
        .select("id, completed_at")
        .eq("user_id", user_id)
        .gte("completed_at", week_start)
        .execute()
    )
    workouts = workouts_result.data or []

    food_result = (
        await client.table("food_logs")
        .select("calories, protein, fat, carbs, logged_at")
        .eq("user_id", user_id)
        .gte("logged_at", week_start)
        .execute()
    )
    food_logs = food_result.data or []

    # Group nutrition by day
    days_data: dict[str, dict] = {}
    for row in food_logs:
        day = row["logged_at"][:10]
        if day not in days_data:
            days_data[day] = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
        days_data[day]["calories"] += row["calories"]
        days_data[day]["protein"] += row["protein"]
        days_data[day]["fat"] += row["fat"]
        days_data[day]["carbs"] += row["carbs"]

    n_days = len(days_data)
    avg_calories = round(sum(d["calories"] for d in days_data.values()) / n_days) if n_days else 0
    avg_protein = round(sum(d["protein"] for d in days_data.values()) / n_days, 1) if n_days else 0

    weight_result = (
        await client.table("progress_logs")
        .select("weight_kg, measured_at")
        .eq("user_id", user_id)
        .gte("measured_at", week_start)
        .order("measured_at")
        .execute()
    )
    weight_logs = weight_result.data or []
    weight_change = None
    if len(weight_logs) >= 2:
        weight_change = round(weight_logs[-1]["weight_kg"] - weight_logs[0]["weight_kg"], 1)

    # Get norms from nutrition tool
    from agent.tools.nutrition import calculate_daily_calories

    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})
    norm_calories = norms.get("calories", 2000)
    norm_protein = norms.get("protein_g", 150)

    protein_compliance_pct = round(avg_protein / norm_protein * 100) if norm_protein > 0 else 0
    calorie_compliance_pct = round(avg_calories / norm_calories * 100) if norm_calories > 0 else 0

    return {
        "period": "последние 7 дней",
        "workouts": {
            "count": len(workouts),
            "recommendation": "Целевой минимум — 3 тренировки в неделю",
        },
        "nutrition": {
            "days_logged": n_days,
            "avg_calories": avg_calories,
            "norm_calories": norm_calories,
            "calorie_compliance_pct": calorie_compliance_pct,
            "avg_protein_g": avg_protein,
            "norm_protein_g": norm_protein,
            "protein_compliance_pct": protein_compliance_pct,
            "protein_note": (
                "✅ Норма белка выполнена" if protein_compliance_pct >= 90
                else f"⚠️ Белка недостаточно ({protein_compliance_pct}% от нормы)"
            ),
        },
        "weight": {
            "change_kg": weight_change,
            "measurements": len(weight_logs),
        },
    }


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
