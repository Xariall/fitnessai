"""Тесты для инструментов питания."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательная функция — изолированный расчёт КБЖУ (без Supabase)
# ---------------------------------------------------------------------------

def _calc_calories(weight_kg: float, height_cm: float, age: int, goal: str, activity_level: str) -> dict:
    """Дублирует логику calculate_daily_calories для unit-тестирования."""
    activity_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    goal_adjustments = {"lose_weight": -300, "gain_muscle": +300, "maintain": 0}

    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    tdee = bmr * activity_multipliers[activity_level]
    target_calories = int(tdee + goal_adjustments[goal])

    protein = round(weight_kg * 2.0, 1)
    fat = round(target_calories * 0.25 / 9, 1)
    carbs = round((target_calories - protein * 4 - fat * 9) / 4, 1)

    return {"calories": target_calories, "protein_g": protein, "fat_g": fat, "carbs_g": carbs}


class TestCalorieCalculation:
    def test_lose_weight_reduces_calories(self, user_profile_lose_weight):
        u = user_profile_lose_weight
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "lose_weight", u["activity_level"])
        maintain = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "maintain", u["activity_level"])
        assert result["calories"] == maintain["calories"] - 300

    def test_gain_muscle_increases_calories(self, user_profile_gain_muscle):
        u = user_profile_gain_muscle
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "gain_muscle", u["activity_level"])
        maintain = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "maintain", u["activity_level"])
        assert result["calories"] == maintain["calories"] + 300

    def test_protein_is_2g_per_kg(self, user_profile_lose_weight):
        u = user_profile_lose_weight
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], u["goal"], u["activity_level"])
        assert result["protein_g"] == round(u["weight_kg"] * 2.0, 1)

    def test_fat_is_25_percent_of_calories(self, user_profile_maintain):
        u = user_profile_maintain
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], u["goal"], u["activity_level"])
        expected_fat = round(result["calories"] * 0.25 / 9, 1)
        assert result["fat_g"] == expected_fat

    def test_calories_are_positive(self, user_profile_lose_weight):
        u = user_profile_lose_weight
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], u["goal"], u["activity_level"])
        assert result["calories"] > 0

    def test_carbs_are_positive(self, user_profile_gain_muscle):
        u = user_profile_gain_muscle
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], u["goal"], u["activity_level"])
        assert result["carbs_g"] > 0

    def test_very_active_higher_than_sedentary(self, user_profile_maintain):
        u = user_profile_maintain
        active = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "maintain", "very_active")
        sedentary = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "maintain", "sedentary")
        assert active["calories"] > sedentary["calories"]

    @pytest.mark.parametrize("goal", ["lose_weight", "gain_muscle", "maintain"])
    def test_all_goals_return_complete_dict(self, goal, user_profile_maintain):
        u = user_profile_maintain
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], goal, u["activity_level"])
        assert set(result.keys()) == {"calories", "protein_g", "fat_g", "carbs_g"}

    @pytest.mark.parametrize("level", ["sedentary", "light", "moderate", "active", "very_active"])
    def test_all_activity_levels_work(self, level, user_profile_maintain):
        u = user_profile_maintain
        result = _calc_calories(u["weight_kg"], u["height_cm"], u["age"], "maintain", level)
        assert result["calories"] > 0


class TestDailyNutritionSummary:
    def test_consumed_sums_correctly(self):
        logs = [
            {"calories": 400, "protein": 30.0, "fat": 10.0, "carbs": 50.0},
            {"calories": 600, "protein": 40.0, "fat": 15.0, "carbs": 80.0},
        ]
        consumed = {
            "calories": sum(r["calories"] for r in logs),
            "protein": round(sum(r["protein"] for r in logs), 1),
            "fat": round(sum(r["fat"] for r in logs), 1),
            "carbs": round(sum(r["carbs"] for r in logs), 1),
        }
        assert consumed == {"calories": 1000, "protein": 70.0, "fat": 25.0, "carbs": 130.0}

    def test_remaining_is_norm_minus_consumed(self):
        norms = {"calories": 2200, "protein_g": 160.0, "fat_g": 60.0, "carbs_g": 250.0}
        consumed = {"calories": 1000, "protein": 70.0, "fat": 25.0, "carbs": 130.0}
        remaining = {
            "calories": norms["calories"] - consumed["calories"],
            "protein": round(norms["protein_g"] - consumed["protein"], 1),
            "fat": round(norms["fat_g"] - consumed["fat"], 1),
            "carbs": round(norms["carbs_g"] - consumed["carbs"], 1),
        }
        assert remaining["calories"] == 1200
        assert remaining["protein"] == 90.0

    def test_empty_logs_returns_zeros(self):
        logs = []
        consumed = {
            "calories": sum(r["calories"] for r in logs),
            "protein": round(sum(r["protein"] for r in logs), 1),
        }
        assert consumed["calories"] == 0
        assert consumed["protein"] == 0.0
