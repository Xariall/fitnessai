import logging
from datetime import date, datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from agent.constants import ACTIVITY_MULTIPLIERS as _ACTIVITY_MULTIPLIERS, GOAL_ADJUSTMENTS as _GOAL_ADJUSTMENTS
from db.client import get_client
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)


@tool
async def calculate_daily_calories(telegram_user_id: int) -> dict:
    """Рассчитать суточную норму КБЖУ по формуле Миффлина-Сан Жеора с учётом цели."""
    client = await get_client()
    result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    if not result.data:
        return {}

    u = result.data
    # Формула Миффлина-Сан Жеора (для мужчины; +5 для женщины замени на -161)
    bmr = 10 * u["weight_kg"] + 6.25 * u["height_cm"] - 5 * u["age"] + 5
    tdee = bmr * _ACTIVITY_MULTIPLIERS.get(u["activity_level"], 1.55)
    target_calories = int(tdee + _GOAL_ADJUSTMENTS.get(u["goal"], 0))

    # Белок: 2 г/кг; жиры: 25% от калорий; углеводы: остаток
    protein = round(u["weight_kg"] * 2.0, 1)
    fat = round(target_calories * 0.25 / 9, 1)
    carbs = round((target_calories - protein * 4 - fat * 9) / 4, 1)

    return {
        "calories": target_calories,
        "protein_g": protein,
        "fat_g": fat,
        "carbs_g": carbs,
    }


@tool
async def generate_nutrition_plan(
    telegram_user_id: int,
    preferences: Optional[str] = None,
) -> dict:
    """Сгенерировать план питания на день с конкретными блюдами.

    Автоматически включает уже записанные сегодня приёмы пищи и генерирует
    только оставшиеся под оставшийся калорийный бюджет.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        preferences: Предпочтения или ограничения (непереносимости, вкусы).
    """
    import json, re
    from llm.provider import get_llm

    _MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]
    _MEAL_LABELS = {"breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин", "snack": "Перекус"}

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})
    user_id = await _get_user_id(telegram_user_id)

    # ── Читаем сегодняшние логи ────────────────────────────────────────────────
    today_logs: list[dict] = []
    if user_id:
        today = date.today().isoformat()
        logs_result = (
            await client.table("food_logs")
            .select("food_name, meal_type, calories, protein, fat, carbs")
            .eq("user_id", user_id)
            .gte("logged_at", f"{today}T00:00:00")
            .execute()
        )
        today_logs = logs_result.data or []

    # ── Группируем уже съеденное по приёму пищи ───────────────────────────────
    consumed_by_meal: dict[str, list] = {}
    for log in today_logs:
        consumed_by_meal.setdefault(log["meal_type"], []).append(log)

    # Строим meal-объекты из реальных данных БД (не из LLM)
    consumed_meals: list[dict] = []
    consumed_cal = consumed_prot = consumed_fat = consumed_carb = 0.0
    for mt in _MEAL_ORDER:
        if mt not in consumed_by_meal:
            continue
        items = consumed_by_meal[mt]
        mt_cal = sum(i["calories"] for i in items)
        mt_prot = round(sum(i["protein"] for i in items), 1)
        mt_fat = round(sum(i["fat"] for i in items), 1)
        mt_carb = round(sum(i["carbs"] for i in items), 1)
        consumed_meals.append({
            "type": mt,
            "label": _MEAL_LABELS[mt],
            "already_eaten": True,
            "items": [
                {"name": i["food_name"], "calories": i["calories"],
                 "protein": i["protein"], "fat": i["fat"], "carbs": i["carbs"]}
                for i in items
            ],
            "total_calories": mt_cal,
        })
        consumed_cal += mt_cal
        consumed_prot += mt_prot
        consumed_fat += mt_fat
        consumed_carb += mt_carb

    # ── Считаем оставшийся бюджет ─────────────────────────────────────────────
    remaining_cal = norms.get("calories", 0) - int(consumed_cal)
    remaining_prot = round(norms.get("protein_g", 0) - consumed_prot, 1)
    remaining_fat = round(norms.get("fat_g", 0) - consumed_fat, 1)
    remaining_carb = round(norms.get("carbs_g", 0) - consumed_carb, 1)

    remaining_types = [mt for mt in _MEAL_ORDER if mt not in consumed_by_meal]

    # ── LLM генерирует только оставшиеся приёмы ───────────────────────────────
    generated_meals: list[dict] = []
    if remaining_types and remaining_cal > 50:
        llm = get_llm()
        pref_text = f"Предпочтения / ограничения: {preferences}." if preferences else ""
        types_str = ", ".join(f"{_MEAL_LABELS[mt]} ({mt})" for mt in remaining_types)
        json_schema = (
            '{"meals": [{"type": "breakfast|lunch|dinner|snack", "label": "...", '
            '"items": [{"name": "...", "calories": int, "protein": float, "fat": float, "carbs": float}], '
            '"total_calories": int}]}'
        )
        prompt = (
            f"Составь план питания только для приёмов: {types_str}.\n"
            f"Профиль: вес {profile.get('weight_kg')} кг, цель: {profile.get('goal')}.\n"
            f"Оставшийся бюджет: {remaining_cal} ккал | "
            f"Б {remaining_prot}г | Ж {remaining_fat}г | У {remaining_carb}г.\n"
            f"{pref_text}\n\n"
            f"ВАЖНО:\n"
            f"- Вес блюда в граммах ГОТОВОГО продукта\n"
            f"- Реалистичные КБЖУ: овсянка варёная 100г=88 ккал, гречка варёная 100г=110 ккал, "
            f"куриная грудка 100г=165 ккал, яйцо=75 ккал, творог 5% 100г=121 ккал\n"
            f"- 1-3 блюда на приём\n"
            f"- Суммарные калории всех приёмов ≈ {remaining_cal} ккал\n\n"
            f"Верни ТОЛЬКО JSON без пояснений:\n{json_schema}"
        )
        try:
            response = await llm.ainvoke(prompt)
            raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group()) if match else {"meals": []}
            generated_meals = parsed.get("meals", [])
        except Exception:
            logger.warning("LLM call/parse failed in generate_nutrition_plan for user %s", telegram_user_id)

    # ── Собираем финальный план ────────────────────────────────────────────────
    all_meals = consumed_meals + generated_meals
    all_items = [item for meal in all_meals for item in meal.get("items", [])]
    daily_total = {
        "calories": sum(i["calories"] for i in all_items),
        "protein": round(sum(i["protein"] for i in all_items), 1),
        "fat": round(sum(i["fat"] for i in all_items), 1),
        "carbs": round(sum(i["carbs"] for i in all_items), 1),
    }
    plan = {"meals": all_meals, "daily_total": daily_total, "norms": norms}

    if user_id:
        try:
            await client.table("nutrition_plans").insert({
                "user_id": user_id,
                "target_calories": norms.get("calories", 0),
                "target_protein": norms.get("protein_g", 0),
                "target_fat": norms.get("fat_g", 0),
                "target_carbs": norms.get("carbs_g", 0),
                "plan": plan,
            }).execute()
        except Exception:
            logger.exception("Failed to save nutrition_plan to DB for user %s", telegram_user_id)

    return plan


@tool
async def log_food(
    telegram_user_id: int,
    food_name: str,
    meal_type: str,
    calories: int,
    protein: float,
    fat: float,
    carbs: float,
) -> str:
    """Записать приём пищи и вернуть дневной итог.

    meal_type: breakfast | lunch | dinner | snack
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return "Пользователь не найден."

    client = await get_client()
    await client.table("food_logs").insert(
        {
            "user_id": user_id,
            "food_name": food_name,
            "meal_type": meal_type,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    summary = await get_daily_nutrition_summary.ainvoke({"telegram_user_id": telegram_user_id})
    consumed = summary.get("consumed", {})
    return (
        f"✅ Записано: {food_name} — {calories} ккал\n"
        f"За сегодня: {consumed.get('calories', 0)} ккал / "
        f"Б {consumed.get('protein', 0)} г / "
        f"Ж {consumed.get('fat', 0)} г / "
        f"У {consumed.get('carbs', 0)} г"
    )


@tool
async def get_daily_nutrition_summary(telegram_user_id: int) -> dict:
    """Получить сводку по питанию за сегодня: потреблено, осталось до нормы, список записей."""
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {}

    today = date.today().isoformat()
    client = await get_client()
    logs_result = (
        await client.table("food_logs")
        .select("*")
        .eq("user_id", user_id)
        .gte("logged_at", f"{today}T00:00:00")
        .execute()
    )
    logs = logs_result.data or []

    consumed = {
        "calories": sum(r["calories"] for r in logs),
        "protein": round(sum(r["protein"] for r in logs), 1),
        "fat": round(sum(r["fat"] for r in logs), 1),
        "carbs": round(sum(r["carbs"] for r in logs), 1),
    }

    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})
    remaining = {
        "calories": norms.get("calories", 0) - consumed["calories"],
        "protein": round(norms.get("protein_g", 0) - consumed["protein"], 1),
        "fat": round(norms.get("fat_g", 0) - consumed["fat"], 1),
        "carbs": round(norms.get("carbs_g", 0) - consumed["carbs"], 1),
    }

    return {"consumed": consumed, "remaining": remaining, "logs": logs}


@tool
async def get_workout_nutrition_protocol(
    telegram_user_id: int,
    workout_time: str,
    workout_type: str = "strength",
    workout_duration_minutes: int = 60,
) -> dict:
    """Get pre/post workout nutrition recommendations (nutrient timing).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        workout_time: Время тренировки, например "18:00".
        workout_type: Тип тренировки (strength / cardio / flexibility).
        workout_duration_minutes: Длительность тренировки в минутах.
    """
    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("weight_kg, goal")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    weight = profile.get("weight_kg", 75)
    goal = profile.get("goal", "maintain")

    pre_carbs_g = round(weight * 0.5)
    pre_protein_g = 25
    post_protein_g = 35 if goal == "gain_muscle" else 25
    post_carbs_g = round(weight * 0.5)
    intra_needed = workout_duration_minutes > 60

    try:
        h, m = workout_time.split(":")
        h = int(h)
        pre_time = f"{(h - 2) % 24:02d}:{m}"
        post_time = f"{(h + 1) % 24:02d}:{m}"
    except Exception:
        pre_time = "за 1.5–2 ч до"
        post_time = "в течение 2 ч после"

    return {
        "workout_time": workout_time,
        "workout_type": workout_type,
        "pre_workout": {
            "time": pre_time,
            "label": "за 1.5–2 часа до тренировки",
            "carbs_g": pre_carbs_g,
            "protein_g": pre_protein_g,
            "fat_note": "минимум — замедляет усвоение",
            "examples": ["Гречка + куриная грудка", "Рис + рыба", "Овсянка + яйца"],
        },
        "post_workout": {
            "time": post_time,
            "label": "в течение 2 часов после тренировки",
            "protein_g": post_protein_g,
            "carbs_g": post_carbs_g,
            "leucine_note": "Минимум 2–3 г лейцина для активации mTOR (курица, яйца, творог)",
            "examples": ["Куриная грудка + рис", "Творог + банан", "Протеин + фрукт"],
            "calorie_note": "Держи порцию строго — цель: похудение" if goal == "lose_weight" else "",
        },
        "intra_workout": {
            "needed": intra_needed,
            "suggestion": "Изотоник или банан + вода" if intra_needed else None,
            "note": (
                "При тренировке >60 мин добавь быстрые углеводы и электролиты"
                if intra_needed
                else "Тренировка <60 мин — intra-питание не нужно"
            ),
        },
        "anabolic_window": "Анаболическое окно — 2 ч до и после. Не нужно есть сразу после тренировки.",
    }


@tool
async def check_nutrition_adjustment(telegram_user_id: int) -> dict:
    """Analyze 4-week weight trend and suggest calorie adjustment if results don't match goal.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    from datetime import datetime, timedelta, timezone

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"status": "no_data", "message": "Пользователь не найден."}

    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}
    goal = profile.get("goal", "maintain")

    since = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()
    logs_result = (
        await client.table("progress_logs")
        .select("weight_kg, measured_at")
        .eq("user_id", user_id)
        .gte("measured_at", since)
        .order("measured_at")
        .execute()
    )
    logs = logs_result.data or []

    if len(logs) < 2:
        return {
            "status": "insufficient_data",
            "message": (
                f"Нужно минимум 2 замера веса за 4 недели для анализа. "
                f"Пока есть {len(logs)} замер(а). Продолжай записывать вес!"
            ),
            "logs_count": len(logs),
        }

    start_w = logs[0]["weight_kg"]
    end_w = logs[-1]["weight_kg"]
    delta = round(end_w - start_w, 2)

    norms = await calculate_daily_calories.ainvoke({"telegram_user_id": telegram_user_id})
    current_calories = norms.get("calories", 2000)

    # BMR — hard floor, never go below
    bmr = int(
        10 * profile.get("weight_kg", 70)
        + 6.25 * profile.get("height_cm", 170)
        - 5 * profile.get("age", 30)
        + 5
    )

    adjustment = 0
    status = "on_track"
    recommendation = ""

    if goal == "lose_weight":
        if delta >= -0.5:
            adjustment = -150
            status = "adjust_needed"
            recommendation = (
                f"За 4 недели вес изменился на {delta:+.1f} кг — слишком мало для похудения. "
                "Уменьши калории на 100–150 ккал."
            )
        else:
            recommendation = f"Всё идёт по плану — потеря {abs(delta):.1f} кг за 4 недели ✅"
    elif goal == "gain_muscle":
        if delta <= 0.3:
            adjustment = +150
            status = "adjust_needed"
            recommendation = (
                f"За 4 недели вес изменился на {delta:+.1f} кг — недостаточно для набора. "
                "Увеличь калории на 100–150 ккал."
            )
        else:
            recommendation = f"Набор идёт — +{delta:.1f} кг за 4 недели ✅"
    else:
        if abs(delta) > 1.0:
            adjustment = -100 if delta > 0 else +100
            status = "adjust_needed"
            recommendation = (
                f"Вес изменился на {delta:+.1f} кг — нужна небольшая корректировка для поддержания."
            )
        else:
            recommendation = "Вес держится стабильно ✅"

    suggested = max(current_calories + adjustment, bmr)
    if suggested == bmr and adjustment < 0:
        recommendation += f" ⚠️ Ниже базального метаболизма ({bmr} ккал) не опускаем."

    # Diet break suggestion after 8+ weeks of deficit
    start_dt = datetime.fromisoformat(logs[0]["measured_at"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(logs[-1]["measured_at"].replace("Z", "+00:00"))
    weeks_tracked = round((end_dt - start_dt).days / 7, 1)
    diet_break_note = None
    if goal == "lose_weight" and weeks_tracked >= 8:
        diet_break_note = (
            "🔄 После 8–12 недель дефицита рекомендуется diet break: "
            "2 недели на поддерживающих калориях — это снижает метаболическую адаптацию."
        )

    return {
        "status": status,
        "goal": goal,
        "weight_delta_kg": delta,
        "weeks_analyzed": weeks_tracked,
        "current_calories": current_calories,
        "suggested_calories": suggested,
        "adjustment_kcal": adjustment,
        "recommendation": recommendation,
        "diet_break_note": diet_break_note,
        "bmr": bmr,
    }


@tool
async def calculate_hydration(
    telegram_user_id: int,
    workout_duration_minutes: int = 0,
    temperature_celsius: int = 20,
) -> dict:
    """Calculate daily water intake recommendation based on weight, workout, and temperature.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        workout_duration_minutes: Длительность тренировки в минутах (0 = день отдыха).
        temperature_celsius: Температура окружающей среды в Цельсиях.
    """
    client = await get_client()
    profile_result = (
        await client.table("users")
        .select("weight_kg")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    weight = (profile_result.data or {}).get("weight_kg", 70)

    base_ml = round(weight * 32)
    workout_ml = round(workout_duration_minutes / 60 * 625) if workout_duration_minutes > 0 else 0
    heat_ml = 500 if temperature_celsius > 25 else 0
    total_ml = base_ml + workout_ml + heat_ml

    electrolytes_needed = workout_duration_minutes > 60

    return {
        "weight_kg": weight,
        "base_ml": base_ml,
        "workout_addition_ml": workout_ml,
        "heat_addition_ml": heat_ml,
        "total_ml": total_ml,
        "total_liters": round(total_ml / 1000, 1),
        "glasses_250ml": round(total_ml / 250),
        "electrolytes_needed": electrolytes_needed,
        "electrolytes_note": (
            "При тренировке >60 мин добавь электролиты: натрий, калий, магний "
            "(изотоник, кокосовая вода, банан + щепотка соли)"
            if electrolytes_needed
            else None
        ),
        "urine_color_guide": (
            "Светло-жёлтая моча = хорошая гидратация. "
            "Тёмная = пей больше. Прозрачная = возможен избыток."
        ),
    }


@tool
async def get_food_info(food_name: str, weight_grams: Optional[int] = None) -> dict:
    """Получить КБЖУ продукта. Использует встроенную базу или LLM-запрос.

    Args:
        food_name: Название продукта или блюда.
        weight_grams: Вес в граммах (по умолчанию 100 г).
    """
    import json, re
    from llm.provider import get_llm

    grams = weight_grams or 100
    llm = get_llm()
    prompt = (
        f"Дай КБЖУ для \"{food_name}\" на {grams} г.\n"
        f"Верни JSON: {{\"calories\": int, \"protein\": float, \"fat\": float, \"carbs\": float}}\n"
        f"Только JSON, без пояснений."
    )
    try:
        response = await llm.ainvoke(prompt)
        raw = re.sub(r"```(?:json)?", "", response.content or "").strip()
    except Exception:
        logger.exception("LLM call failed in get_food_info for %s", food_name)
        return {"food_name": food_name, "weight_grams": grams, "error": "Не удалось получить данные"}

    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group()) if match else {}
    except json.JSONDecodeError:
        logger.warning("JSON parse failed in get_food_info for %s, raw=%r", food_name, raw[:100])
        data = {}

    return {**data, "food_name": food_name, "weight_grams": grams}
