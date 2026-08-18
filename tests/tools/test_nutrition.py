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


class TestNutritionPreferences:
    """get_nutrition_preferences / save_nutrition_preferences — настройки питания
    (продукты дома, вкусы, бюджет), собираемые до первого плана питания."""

    async def test_get_preferences_returns_empty_dict_when_not_set(self):
        from agent.tools.nutrition import get_nutrition_preferences

        fetchrow_mock = AsyncMock(return_value={"nutrition_preferences": None})
        with patch("agent.tools.nutrition.fetchrow", fetchrow_mock):
            result = await get_nutrition_preferences.ainvoke({"telegram_user_id": 123456})

        assert result == {}

    async def test_get_preferences_returns_empty_dict_when_user_not_found(self):
        from agent.tools.nutrition import get_nutrition_preferences

        fetchrow_mock = AsyncMock(return_value=None)
        with patch("agent.tools.nutrition.fetchrow", fetchrow_mock):
            result = await get_nutrition_preferences.ainvoke({"telegram_user_id": 999})

        assert result == {}

    async def test_get_preferences_returns_saved_values(self):
        from agent.tools.nutrition import get_nutrition_preferences

        saved = {
            "usual_products": "гречка, курица, творог",
            "liked_foods": "плов",
            "disliked_foods": "рыба",
            "food_budget": "60000 тг/мес",
        }
        fetchrow_mock = AsyncMock(return_value={"nutrition_preferences": saved})
        with patch("agent.tools.nutrition.fetchrow", fetchrow_mock):
            result = await get_nutrition_preferences.ainvoke({"telegram_user_id": 123456})

        assert result == saved

    async def test_save_preferences_writes_jsonb_dict(self):
        from agent.tools.nutrition import save_nutrition_preferences

        execute_mock = AsyncMock(return_value="UPDATE 1")
        with patch("agent.tools.nutrition.execute", execute_mock):
            result = await save_nutrition_preferences.ainvoke({
                "telegram_user_id": 123456,
                "usual_products": "гречка, курица",
                "liked_foods": "плов",
                "disliked_foods": "рыба",
                "food_budget": "60000 тг/мес",
            })

        assert "✅" in result
        sql, args = execute_mock.call_args.args[0], execute_mock.call_args.args[1:]
        assert "UPDATE users SET nutrition_preferences" in sql
        prefs_arg, telegram_id_arg = args
        assert telegram_id_arg == 123456
        assert prefs_arg == {
            "usual_products": "гречка, курица",
            "liked_foods": "плов",
            "disliked_foods": "рыба",
            "food_budget": "60000 тг/мес",
        }

    async def test_save_preferences_reports_user_not_found(self):
        from agent.tools.nutrition import save_nutrition_preferences

        execute_mock = AsyncMock(return_value="UPDATE 0")
        with patch("agent.tools.nutrition.execute", execute_mock):
            result = await save_nutrition_preferences.ainvoke({
                "telegram_user_id": 999,
                "usual_products": "гречка",
                "liked_foods": "плов",
                "disliked_foods": "",
                "food_budget": "",
            })

        assert result == "Пользователь не найден."


class TestGenerateNutritionPlanUsesPreferences:
    """generate_nutrition_plan должен подмешивать сохранённые настройки питания
    и требование рынка СНГ/Казахстан в промпт LLM."""

    async def test_prompt_includes_saved_preferences_and_cis_market_rule(self):
        from agent.tools.nutrition import generate_nutrition_plan

        profile_row = {
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "age": 30,
            "goal": "maintain",
            "activity_level": "moderate",
            "nutrition_preferences": {
                "usual_products": "гречка, курица, творог",
                "liked_foods": "плов",
                "disliked_foods": "рыба",
                "food_budget": "60000 тг/мес",
            },
        }
        fetchrow_mock = AsyncMock(return_value=profile_row)
        fetch_mock = AsyncMock(return_value=[])  # нет сегодняшних логов
        execute_mock = AsyncMock(return_value="INSERT 0 1")

        llm_response = MagicMock()
        llm_response.content = (
            '{"meals": [{"type": "breakfast", "label": "Завтрак", '
            '"items": [{"name": "Гречка 200г", "calories": 220, "protein": 8, "fat": 2, "carbs": 40}], '
            '"total_calories": 220}]}'
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=llm_response)

        with patch("agent.tools.nutrition.fetchrow", fetchrow_mock), \
             patch("agent.tools.nutrition.fetch", fetch_mock), \
             patch("agent.tools.nutrition.execute", execute_mock), \
             patch("agent.tools.nutrition._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("llm.provider.get_llm", MagicMock(return_value=llm_mock)):
            await generate_nutrition_plan.ainvoke({"telegram_user_id": 123456})

        prompt_sent = llm_mock.ainvoke.call_args.args[0]
        assert "гречка, курица, творог" in prompt_sent
        assert "плов" in prompt_sent
        assert "рыба" in prompt_sent
        assert "60000 тг/мес" in prompt_sent
        assert "Казахстан" in prompt_sent

    async def test_prompt_omits_preferences_block_when_not_set(self):
        from agent.tools.nutrition import generate_nutrition_plan

        profile_row = {
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "age": 30,
            "goal": "maintain",
            "activity_level": "moderate",
            "nutrition_preferences": None,
        }
        fetchrow_mock = AsyncMock(return_value=profile_row)
        fetch_mock = AsyncMock(return_value=[])
        execute_mock = AsyncMock(return_value="INSERT 0 1")

        llm_response = MagicMock()
        llm_response.content = '{"meals": []}'
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=llm_response)

        with patch("agent.tools.nutrition.fetchrow", fetchrow_mock), \
             patch("agent.tools.nutrition.fetch", fetch_mock), \
             patch("agent.tools.nutrition.execute", execute_mock), \
             patch("agent.tools.nutrition._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("llm.provider.get_llm", MagicMock(return_value=llm_mock)):
            await generate_nutrition_plan.ainvoke({"telegram_user_id": 123456})

        prompt_sent = llm_mock.ainvoke.call_args.args[0]
        assert "Настройки питания пользователя:" not in prompt_sent
        assert "Казахстан" in prompt_sent
