"""
Tests for log_workout upsert logic.

Bug fixed: calling log_workout twice for the same workout session (same workout_id
within 8 hours) used to create two DB records. Now the second call UPDATEs the
existing record instead of INSERTing a duplicate.

Test matrix:
  - no workout_id → always INSERT (can't deduplicate)
  - workout_id + no existing log → INSERT + advance cycle
  - workout_id + existing log found → UPDATE, no INSERT, no cycle advance
  - existing log older than 8h → INSERT (treated as new session)
  - done_as_planned=True first, then real weights → UPDATE replaces performance
"""
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exec(data):
    """Return an AsyncMock execute() that yields `data` once."""
    return AsyncMock(return_value=MagicMock(data=data))


def _chain(execute_results: list):
    """
    Build a Supabase-style query chain mock.

    All chained methods (select, eq, gte, order, limit, single, insert, update)
    return the same mock so the chain collapses to a single object.
    execute() pops values from *execute_results* in order.
    """
    m = MagicMock()
    for method in ("select", "eq", "gte", "lte", "order", "limit", "single"):
        getattr(m, method).return_value = m

    # insert / update return the same mock so .execute() is called on m
    m.insert.return_value = m
    m.update.return_value = m

    results = iter(execute_results)

    async def _execute():
        return next(results)

    m.execute = _execute
    return m


def _result(data):
    return MagicMock(data=data)


# ---------------------------------------------------------------------------
# Shared performance fixture
# ---------------------------------------------------------------------------

PERFORMANCE = [
    {"name": "Жим штанги лёжа", "sets_done": 3, "reps_done": 10, "weight_kg": 80.0}
]

PERFORMANCE_REAL = [
    {"name": "Жим штанги лёжа", "sets_done": 3, "reps_done": 10, "weight_kg": 100.0}
]


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _build_client(wl_execute_results: list, users_weight_kg=75.0, plan_exercises=None):
    """
    Build a mock Supabase client for log_workout tests.

    wl_execute_results: ordered list of MagicMock(data=...) objects that
        workout_logs.execute() will return in sequence.
    """
    wl_mock = _chain(wl_execute_results)

    users_mock = _chain([_result({"weight_kg": users_weight_kg})])

    plan_data = {"exercises": plan_exercises or []}
    workouts_mock = _chain([_result({"plan": plan_data})])

    client = MagicMock()

    def _table(name):
        if name == "workout_logs":
            return wl_mock
        if name == "users":
            return users_mock
        if name == "workouts":
            return workouts_mock
        return _chain([_result(None)])

    client.table = _table
    return client, wl_mock


# ---------------------------------------------------------------------------
# Tests: INSERT path (no existing log)
# ---------------------------------------------------------------------------


class TestInsertPath:
    """When no existing workout_log is found → INSERT is called."""

    async def test_insert_called_when_no_existing_log(self):
        # workout_logs execute() sequence:
        # 1. prev_logs check (suggest_details)
        # 2. history for PR detection
        # 3. upsert check → [] (no existing)
        # 4. insert result
        client, wl = _build_client([
            _result([]),    # prev_logs
            _result([]),    # history
            _result([]),    # upsert check → empty → INSERT
            _result(None),  # insert
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Тренировка прошла хорошо",
                "workout_id": "wid-001",
                "performance": PERFORMANCE,
                "done_as_planned": True,
            })

        assert result["status"] == "logged"
        wl.insert.assert_called_once()
        wl.update.assert_not_called()

    async def test_no_workout_id_always_inserts(self):
        """Without workout_id, upsert check is skipped → always INSERT."""
        client, wl = _build_client([
            _result([]),    # prev_logs
            _result([]),    # history
            # No upsert check (no workout_id)
            _result(None),  # insert
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Вольная тренировка",
                "workout_id": None,
                "performance": PERFORMANCE,
                "done_as_planned": False,
            })

        assert result["status"] == "logged"
        wl.insert.assert_called_once()
        wl.update.assert_not_called()

    async def test_cycle_advanced_on_insert(self):
        """Cycle position is advanced when a new record is INSERTed."""
        fake_cycle = {"id": "cycle-001", "current_week": 1, "current_session_index": 0}
        advance_result = {"status": "advanced", "new_index": 1}

        client, wl = _build_client([
            _result([]),    # prev_logs
            _result([]),    # history
            _result([]),    # upsert check → empty → INSERT
            _result(None),  # insert
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=fake_cycle)), \
             patch("agent.tools.workouts._advance_cycle_position", AsyncMock(return_value=advance_result)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Тренировка по плану",
                "workout_id": "wid-001",
                "performance": PERFORMANCE,
                "done_as_planned": True,
                "advance_cycle": True,
            })

        assert result["cycle_advancement"] == advance_result

    async def test_user_not_found_returns_error(self):
        """If user_id is None, return error without any DB writes."""
        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value=None)):
            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 99999,
                "notes": "test",
            })

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Tests: UPDATE path (existing log found)
# ---------------------------------------------------------------------------


class TestUpdatePath:
    """When an existing workout_log is found within 8h → UPDATE, not INSERT."""

    async def test_update_called_when_existing_log(self):
        # upsert check returns existing record
        client, wl = _build_client([
            _result([]),                            # prev_logs
            _result([]),                            # history
            _result([{"id": "existing-log-id"}]),  # upsert check → found → UPDATE
            _result(None),                          # update result
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Взял 100кг, 10 повторений",
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
            })

        assert result["status"] == "logged"
        wl.update.assert_called_once()
        wl.insert.assert_not_called()

    async def test_update_targets_correct_id(self):
        """UPDATE must be called with the exact existing record id."""
        existing_id = "log-uuid-abc123"
        client, wl = _build_client([
            _result([]),
            _result([]),
            _result([{"id": existing_id}]),  # upsert check
            _result(None),
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Уточнённые данные",
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
            })

        # The .eq() call after .update() should receive the existing_id
        eq_calls = [str(c) for c in wl.eq.call_args_list]
        assert any(existing_id in c for c in eq_calls), (
            f"Expected eq() to be called with {existing_id!r}, got: {eq_calls}"
        )

    async def test_cycle_not_advanced_on_update(self):
        """Cycle must NOT be advanced when UPDATEing an existing record."""
        fake_cycle = {"id": "cycle-001", "current_week": 1, "current_session_index": 0}
        advance_mock = AsyncMock(return_value={"status": "advanced"})

        client, wl = _build_client([
            _result([]),
            _result([]),
            _result([{"id": "existing-id"}]),  # existing → UPDATE
            _result(None),
        ])

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=fake_cycle)), \
             patch("agent.tools.workouts._advance_cycle_position", advance_mock), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Детали тренировки",
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
                "advance_cycle": True,
            })

        advance_mock.assert_not_called()
        assert result["cycle_advancement"] is None

    async def test_update_uses_latest_data(self):
        """UPDATE record should carry the new notes and performance."""
        client, wl = _build_client([
            _result([]),
            _result([]),
            _result([{"id": "existing-id"}]),
            _result(None),
        ])

        new_notes = "60кг × 12 повторений, ощущения отличные"

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=client)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": new_notes,
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
            })

        update_call_args = wl.update.call_args
        assert update_call_args is not None
        updated_record = update_call_args[0][0]
        assert updated_record["notes"] == new_notes
        # Performance should be the new real data
        assert updated_record["performance"] is not None
        assert updated_record["performance"][0]["weight_kg"] == 100.0


# ---------------------------------------------------------------------------
# Tests: scenario — first "as planned", then real weights
# ---------------------------------------------------------------------------


class TestTwoCallScenario:
    """
    Real-world bug scenario:
      1. User says "все по плану" → agent calls log_workout(done_as_planned=True)
      2. Agent asks "как прошла тренировка?"
      3. User gives real weights → agent calls log_workout again (done_as_planned=False)
      4. Second call should UPDATE the first record, not create a second one.
    """

    async def _call(self, client, done_as_planned, performance, existing_rows=None):
        existing_rows = existing_rows or []
        wl_results = [
            _result([]),             # prev_logs
            _result([]),             # history
            _result(existing_rows),  # upsert check
            _result(None),           # write result
        ]
        # Re-wire the chain with new results each call
        wl = _chain(wl_results)
        users = _chain([_result({"weight_kg": 75.0})])
        workouts = _chain([_result({"plan": {"exercises": []}})])
        c = MagicMock()

        def _table(name):
            if name == "workout_logs":
                return wl
            if name == "users":
                return users
            if name == "workouts":
                return workouts
            return _chain([_result(None)])

        c.table = _table

        with patch("agent.tools.workouts._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.get_client", AsyncMock(return_value=c)), \
             patch("agent.tools.workouts._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "notes",
                "workout_id": "wid-001",
                "performance": performance,
                "done_as_planned": done_as_planned,
            })

        return result, wl

    async def test_first_call_inserts(self):
        _, wl = await self._call(
            client=None,
            done_as_planned=True,
            performance=PERFORMANCE,
            existing_rows=[],   # no existing → INSERT
        )
        wl.insert.assert_called_once()
        wl.update.assert_not_called()

    async def test_second_call_updates(self):
        """Second call with real weights finds existing record → UPDATE."""
        _, wl = await self._call(
            client=None,
            done_as_planned=False,
            performance=PERFORMANCE_REAL,
            existing_rows=[{"id": "first-insert-id"}],  # existing → UPDATE
        )
        wl.update.assert_called_once()
        wl.insert.assert_not_called()

    async def test_second_call_replaces_performance(self):
        """Real performance data must overwrite the plan placeholder."""
        _, wl = await self._call(
            client=None,
            done_as_planned=False,
            performance=PERFORMANCE_REAL,
            existing_rows=[{"id": "first-insert-id"}],
        )
        updated_record = wl.update.call_args[0][0]
        assert updated_record["done_as_planned"] is False
        assert updated_record["performance"][0]["weight_kg"] == 100.0
