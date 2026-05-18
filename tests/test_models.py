"""Тесты Pydantic-моделей БД."""
import pytest
from pydantic import ValidationError

from db.models import FoodLog, NutritionPlan, ProgressLog, User, Workout, WorkoutLog


class TestUserModel:
    def test_valid_user(self):
        user = User(
            telegram_user_id=123456,
            name="Алексей",
            age=30,
            weight_kg=90.0,
            height_cm=180.0,
            goal="lose_weight",
            activity_level="moderate",
        )
        assert user.telegram_user_id == 123456
        assert user.goal == "lose_weight"

    def test_optional_id(self):
        user = User(
            telegram_user_id=1,
            name="Test",
            age=25,
            weight_kg=70.0,
            height_cm=175.0,
            goal="maintain",
            activity_level="light",
        )
        assert user.id is None
        assert user.created_at is None

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            User(telegram_user_id=1, name="Test")  # type: ignore[call-arg]

    @pytest.mark.parametrize("goal", ["lose_weight", "gain_muscle", "maintain"])
    def test_valid_goals(self, goal):
        user = User(
            telegram_user_id=1, name="T", age=25, weight_kg=70.0,
            height_cm=175.0, goal=goal, activity_level="light",
        )
        assert user.goal == goal

    @pytest.mark.parametrize("level", ["sedentary", "light", "moderate", "active", "very_active"])
    def test_valid_activity_levels(self, level):
        user = User(
            telegram_user_id=1, name="T", age=25, weight_kg=70.0,
            height_cm=175.0, goal="maintain", activity_level=level,
        )
        assert user.activity_level == level


class TestFoodLogModel:
    def test_valid_food_log(self):
        log = FoodLog(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            food_name="Овсянка",
            calories=300,
            protein=10.0,
            fat=5.0,
            carbs=55.0,
            meal_type="breakfast",
        )
        assert log.food_name == "Овсянка"
        assert log.meal_type == "breakfast"

    @pytest.mark.parametrize("meal_type", ["breakfast", "lunch", "dinner", "snack"])
    def test_valid_meal_types(self, meal_type):
        log = FoodLog(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            food_name="Еда",
            calories=200,
            protein=10.0,
            fat=5.0,
            carbs=30.0,
            meal_type=meal_type,
        )
        assert log.meal_type == meal_type


class TestProgressLogModel:
    def test_valid_progress_log(self):
        log = ProgressLog(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            weight_kg=85.5,
        )
        assert log.weight_kg == 85.5
        assert log.notes is None

    def test_with_notes(self):
        log = ProgressLog(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            weight_kg=85.0,
            notes="Чувствую себя отлично",
        )
        assert log.notes == "Чувствую себя отлично"


class TestNutritionPlanModel:
    def test_valid_plan(self):
        plan = NutritionPlan(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            target_calories=2000,
            target_protein=150.0,
            target_fat=65.0,
            target_carbs=220.0,
            plan={"meals": []},
        )
        assert plan.target_calories == 2000


class TestWorkoutModel:
    def test_valid_workout(self):
        w = Workout(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            title="Тренировка ног",
            plan={"exercises": [{"name": "Приседания", "sets": 4, "reps": "10"}]},
        )
        assert w.title == "Тренировка ног"
        assert len(w.plan["exercises"]) == 1
