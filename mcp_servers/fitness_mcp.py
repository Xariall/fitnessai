"""MCP-сервер: тренировки, упражнения, вес, прогресс."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from database import db

mcp = FastMCP("fitness", instructions="Сервер для работы с тренировками, упражнениями и весом тела.")


@mcp.tool()
async def get_exercises(muscle_group: str | None = None) -> str:
    """Получить список упражнений. Можно фильтровать по группе мышц:
    chest, back, legs, shoulders, arms, abs."""
    exercises = await db.get_exercises(muscle_group)
    if not exercises:
        return "Упражнения не найдены."
    return json.dumps(exercises, ensure_ascii=False)


@mcp.tool()
async def log_workout_entry(
    user_id: str, exercise: str, sets: int, reps: int, weight_kg: float = 0
) -> str:
    """Записать выполненное упражнение в лог тренировок.
    Пример: log_workout_entry('user1', 'Жим штанги лёжа', 3, 10, 80)"""
    await db.log_workout(user_id, exercise, sets, reps, weight_kg or None)
    return f"Записано: {exercise} — {sets}x{reps}" + (
        f" @ {weight_kg}кг" if weight_kg else ""
    )


@mcp.tool()
async def get_workout_logs(user_id: str, date: str | None = None) -> str:
    """Получить историю тренировок пользователя.
    date — опционально, формат 'YYYY-MM-DD'. Без даты — последние 50."""
    logs = await db.get_workout_logs(user_id, date)
    if not logs:
        return "Тренировки не найдены."
    return json.dumps(logs, ensure_ascii=False)


@mcp.tool()
async def log_weight(user_id: str, weight: float) -> str:
    """Записать текущий вес тела. Пример: log_weight('user1', 78.5)"""
    await db.log_weight(user_id, weight)
    return f"Вес {weight} кг записан."


@mcp.tool()
async def get_weight_history(user_id: str, days: int = 30) -> str:
    """Получить историю веса за последние N дней (по умолчанию 30)."""
    history = await db.get_weight_history(user_id, days)
    if not history:
        return "Записей веса не найдено."
    return json.dumps(history, ensure_ascii=False)


@mcp.tool()
async def save_program(
    user_id: str,
    name: str,
    goal: str,
    level: str,
    days_per_week: int,
    program_json: str,
) -> str:
    """Сохранить программу тренировок. program_json — JSON-строка с описанием программы."""
    pid = await db.save_workout_program(
        user_id, name, goal, level, days_per_week, program_json
    )
    return f"Программа '{name}' сохранена (id={pid})."


@mcp.tool()
async def get_programs(user_id: str) -> str:
    """Получить все программы тренировок пользователя."""
    programs = await db.get_workout_programs(user_id)
    if not programs:
        return "Программ не найдено."
    return json.dumps(programs, ensure_ascii=False)


@mcp.tool()
async def get_progress(user_id: str) -> str:
    """Получить сводку прогресса: текущий вес, динамика, кол-во тренировок."""
    weight_history = await db.get_weight_history(user_id, days=30)
    workout_logs = await db.get_workout_logs(user_id)
    user = await db.get_user(user_id)

    progress = {
        "current_weight": user.get("weight") if user else None,
        "weight_entries_30d": len(weight_history),
        "total_workouts": len(workout_logs),
    }

    if len(weight_history) >= 2:
        oldest = weight_history[-1]["weight"]
        newest = weight_history[0]["weight"]
        progress["weight_change_30d"] = round(newest - oldest, 1)

    return json.dumps(progress, ensure_ascii=False)


@mcp.tool()
async def complete_onboarding(
    user_id: str,
    age: int | None = None,
    height: float | None = None,
    weight: float | None = None,
    gender: str | None = None,
    activity: str | None = None,
    goal: str | None = None,
    injuries: str | None = None,
) -> str:
    """Сохранить профиль пользователя и завершить онбординг.

    Вызывай этот инструмент ТОЛЬКО когда собрал все обязательные данные:
    возраст, рост, вес, пол, уровень активности (sedentary/moderate/active/athlete)
    и цель (lose/gain/maintain/recomposition).

    Без вызова этого инструмента пользователь не сможет открыть другие разделы приложения.
    """
    await db.upsert_user_profile(
        int(user_id),
        age=age,
        height=height,
        weight=weight,
        gender=gender,
        activity=activity,
        goal=goal,
        injuries=injuries,
        onboarding_completed=True,
    )
    return json.dumps({"success": True, "message": "Профиль сохранён, онбординг завершён. Все разделы приложения теперь доступны."}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
