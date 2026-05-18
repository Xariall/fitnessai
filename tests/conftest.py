"""Общие фикстуры для тестов."""
import pytest


@pytest.fixture
def user_profile_lose_weight() -> dict:
    return {
        "id": "uuid-1",
        "telegram_user_id": 123456,
        "name": "Алексей",
        "age": 30,
        "weight_kg": 90.0,
        "height_cm": 180.0,
        "goal": "lose_weight",
        "activity_level": "moderate",
    }


@pytest.fixture
def user_profile_gain_muscle() -> dict:
    return {
        "id": "uuid-2",
        "telegram_user_id": 654321,
        "name": "Мария",
        "age": 25,
        "weight_kg": 60.0,
        "height_cm": 165.0,
        "goal": "gain_muscle",
        "activity_level": "active",
    }


@pytest.fixture
def user_profile_maintain() -> dict:
    return {
        "id": "uuid-3",
        "telegram_user_id": 111111,
        "name": "Иван",
        "age": 35,
        "weight_kg": 75.0,
        "height_cm": 175.0,
        "goal": "maintain",
        "activity_level": "light",
    }
