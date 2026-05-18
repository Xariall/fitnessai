"""Тесты для инструментов тренировок."""
import pytest


# База упражнений (зеркало из workouts.py для изолированного тестирования)
_EXERCISE_DB = [
    {"name": "Приседания", "muscle_group": "legs", "equipment": "none"},
    {"name": "Жим штанги лёжа", "muscle_group": "chest", "equipment": "barbell"},
    {"name": "Становая тяга", "muscle_group": "back", "equipment": "barbell"},
    {"name": "Подтягивания", "muscle_group": "back", "equipment": "bar"},
    {"name": "Отжимания", "muscle_group": "chest", "equipment": "none"},
    {"name": "Выпады", "muscle_group": "legs", "equipment": "none"},
    {"name": "Жим гантелей сидя", "muscle_group": "shoulders", "equipment": "dumbbells"},
    {"name": "Сгибания на бицепс", "muscle_group": "biceps", "equipment": "dumbbells"},
    {"name": "Французский жим", "muscle_group": "triceps", "equipment": "barbell"},
    {"name": "Планка", "muscle_group": "core", "equipment": "none"},
    {"name": "Скручивания", "muscle_group": "core", "equipment": "none"},
    {"name": "Бег", "muscle_group": "cardio", "equipment": "none"},
    {"name": "Велосипед", "muscle_group": "cardio", "equipment": "bike"},
    {"name": "Прыжки на скакалке", "muscle_group": "cardio", "equipment": "rope"},
    {"name": "Растяжка квадрицепса", "muscle_group": "flexibility", "equipment": "none"},
    {"name": "Растяжка спины (кошка-корова)", "muscle_group": "flexibility", "equipment": "none"},
]


def _find_exercises(muscle_group: str, equipment: str | None = None) -> list[dict]:
    results = [ex for ex in _EXERCISE_DB if muscle_group.lower() in ex["muscle_group"].lower()]
    if equipment:
        results = [ex for ex in results if equipment.lower() in ex["equipment"].lower()]
    return results


class TestFindExercises:
    def test_find_by_muscle_group(self):
        results = _find_exercises("legs")
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert "Приседания" in names
        assert "Выпады" in names

    def test_find_cardio(self):
        results = _find_exercises("cardio")
        assert len(results) == 3

    def test_find_core(self):
        results = _find_exercises("core")
        assert len(results) == 2

    def test_filter_by_equipment(self):
        results = _find_exercises("back", equipment="barbell")
        assert len(results) == 1
        assert results[0]["name"] == "Становая тяга"

    def test_filter_no_equipment(self):
        results = _find_exercises("chest", equipment="none")
        assert len(results) == 1
        assert results[0]["name"] == "Отжимания"

    def test_unknown_muscle_group_returns_empty(self):
        results = _find_exercises("unknown_muscle")
        assert results == []

    def test_equipment_filter_with_no_match_returns_empty(self):
        results = _find_exercises("legs", equipment="barbell")
        assert results == []

    def test_case_insensitive_muscle_group(self):
        lower = _find_exercises("chest")
        upper = _find_exercises("CHEST")
        assert lower == upper

    @pytest.mark.parametrize("group", ["legs", "chest", "back", "shoulders", "biceps", "triceps", "core", "cardio", "flexibility"])
    def test_all_muscle_groups_have_exercises(self, group):
        results = _find_exercises(group)
        assert len(results) >= 1, f"Нет упражнений для группы: {group}"
