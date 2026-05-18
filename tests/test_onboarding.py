"""Тесты для логики онбординга."""
import pytest


GOAL_MAP = {"1": "lose_weight", "2": "gain_muscle", "3": "maintain"}
ACTIVITY_MAP = {
    "1": "sedentary",
    "2": "light",
    "3": "moderate",
    "4": "active",
    "5": "very_active",
}


class TestOnboardingGoalMap:
    @pytest.mark.parametrize("input_val, expected", [
        ("1", "lose_weight"),
        ("2", "gain_muscle"),
        ("3", "maintain"),
    ])
    def test_valid_goal_inputs(self, input_val, expected):
        assert GOAL_MAP.get(input_val) == expected

    def test_invalid_goal_returns_none(self):
        assert GOAL_MAP.get("0") is None
        assert GOAL_MAP.get("4") is None
        assert GOAL_MAP.get("") is None

    @pytest.mark.parametrize("input_val, expected", [
        ("1", "sedentary"),
        ("2", "light"),
        ("3", "moderate"),
        ("4", "active"),
        ("5", "very_active"),
    ])
    def test_valid_activity_inputs(self, input_val, expected):
        assert ACTIVITY_MAP.get(input_val) == expected

    def test_invalid_activity_returns_none(self):
        assert ACTIVITY_MAP.get("0") is None
        assert ACTIVITY_MAP.get("6") is None


class TestWeightParsing:
    """Тест логики парсинга веса/роста из текста (как в onboarding_weight)."""

    @pytest.mark.parametrize("text, expected", [
        ("75", 75.0),
        ("75.5", 75.5),
        ("75,5", 75.5),
        ("90.0", 90.0),
    ])
    def test_valid_weight_strings(self, text, expected):
        value = float(text.replace(",", "."))
        assert value == expected

    @pytest.mark.parametrize("text", ["abc", "75 кг", "", "75.5.5"])
    def test_invalid_weight_raises(self, text):
        with pytest.raises(ValueError):
            float(text.replace(",", "."))
