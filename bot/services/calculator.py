"""Калькулятор BMR / TDEE / БЖУ по формуле Миффлина-Сан Жеора."""


def calculate_nutrition(
    weight: float,
    height: float,
    age: int,
    gender: str,
    activity_level: str,
    goal: str,
) -> dict:
    """
    Рассчитывает BMR, TDEE, целевые калории и макронутриенты.

    Параметры используют DB-значения (английские ключи):
      gender:         'male' | 'female'
      activity_level: 'sedentary' | 'moderate' | 'active' | 'athlete'
      goal:           'lose' | 'maintain' | 'gain' | 'recomposition'
    """

    # ── 1. BMR (Формула Миффлина-Сан Жеора) ──────────────────────────
    if gender == "male":
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

    # ── 2. TDEE = BMR × коэффициент активности ───────────────────────
    activity_multipliers = {
        "sedentary": 1.2,       # Офис, нет тренировок
        "moderate": 1.375,      # Лёгкие тренировки 1-3 р/неделю
        "active": 1.55,         # Умеренные тренировки 3-5 р/неделю
        "athlete": 1.725,       # Тяжёлые тренировки 6-7 р/неделю
    }
    tdee = bmr * activity_multipliers.get(activity_level, 1.2)

    # ── 3. Целевая калорийность (±15%) ────────────────────────────────
    goal_adjustments = {
        "lose": 0.85,           # Дефицит 15%
        "gain": 1.15,           # Профицит 15%
        "maintain": 1.0,        # Поддержание
        "recomposition": 1.0,   # Рекомпозиция = норма
    }
    target_calories = tdee * goal_adjustments.get(goal, 1.0)

    # ── 4. Макронутриенты (БЖУ) ──────────────────────────────────────
    # Белки: 2 г/кг  (1 г = 4 ккал)
    # Жиры:  1 г/кг  (1 г = 9 ккал)
    # Углеводы: остаток калорий / 4
    protein = weight * 2.0
    fat = weight * 1.0
    calories_from_pf = (protein * 4) + (fat * 9)
    carbs = max((target_calories - calories_from_pf) / 4, 50.0)

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": round(target_calories),
        "protein": round(protein),
        "fat": round(fat),
        "carbs": round(carbs),
    }
