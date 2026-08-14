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
import re
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patches(fetchrow_results: list, fetch_results: list | None = None):
    """Patch agent.tools.workouts.session_log's fetchrow/fetch/execute.

    fetchrow_results: values returned by successive fetchrow() calls, in call order.
    fetch_results: values returned by successive fetch() calls, in call order
        (defaults to a single empty-list result — most tests only call fetch()
        once, for PR-detection history).
    """
    fetchrow_mock = AsyncMock(side_effect=fetchrow_results)
    fetch_mock = AsyncMock(side_effect=fetch_results if fetch_results is not None else [[]])
    execute_mock = AsyncMock(return_value="OK")
    return fetchrow_mock, fetch_mock, execute_mock


def _last_sql_and_args(execute_mock) -> tuple[str, tuple]:
    call = execute_mock.call_args
    return call.args[0], call.args[1:]


def _update_record(execute_mock) -> dict:
    """Reconstruct the {column: value} dict from an UPDATE ... SET a=$1,b=$2 ... WHERE id=$n call."""
    sql, args = _last_sql_and_args(execute_mock)
    set_clause = sql.split(" SET ", 1)[1].split(" WHERE ")[0]
    columns = re.findall(r"(\w+) = \$\d+", set_clause)
    return dict(zip(columns, args[:-1]))  # last arg is the WHERE id


PERFORMANCE = [
    {"name": "Жим штанги лёжа", "sets_done": 3, "reps_done": 10, "weight_kg": 80.0}
]

PERFORMANCE_REAL = [
    {"name": "Жим штанги лёжа", "sets_done": 3, "reps_done": 10, "weight_kg": 100.0}
]

PROFILE_ROW = {"weight_kg": 75.0}
EMPTY_PLAN_ROW = {"plan": {"exercises": []}}


# ---------------------------------------------------------------------------
# Tests: INSERT path (no existing log)
# ---------------------------------------------------------------------------


class TestInsertPath:
    """When no existing workout_log is found → INSERT is called."""

    async def test_insert_called_when_no_existing_log(self):
        # fetchrow() sequence: profile, prev_log (none), existing-log check (none)
        fetchrow_mock, fetch_mock, execute_mock = _patches(
            [PROFILE_ROW, None, None]
        )

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
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
        sql, _ = _last_sql_and_args(execute_mock)
        assert sql.strip().startswith("INSERT")

    async def test_no_workout_id_always_inserts(self):
        """Without workout_id, upsert check is skipped → always INSERT."""
        # fetchrow() sequence: profile, prev_log (none) — no existing-log check, no workout_id
        fetchrow_mock, fetch_mock, execute_mock = _patches([PROFILE_ROW, None])

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
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
        sql, _ = _last_sql_and_args(execute_mock)
        assert sql.strip().startswith("INSERT")

    async def test_cycle_advanced_on_insert(self):
        """Cycle position is advanced when a new record is INSERTed."""
        fake_cycle = {"id": "cycle-001", "current_week": 1, "current_session_index": 0}
        advance_result = {"status": "advanced", "new_index": 1}

        fetchrow_mock, fetch_mock, execute_mock = _patches([PROFILE_ROW, None, None])

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=fake_cycle)), \
             patch("agent.tools.workouts.session_log._advance_cycle_position", AsyncMock(return_value=advance_result)), \
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
        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value=None)):
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
        # done_as_planned=False + workout_id + real performance → next_session
        # block also reads the plan, so fetchrow order is:
        # profile, prev_log (none), plan (for next_session), existing-log check (found)
        fetchrow_mock, fetch_mock, execute_mock = _patches(
            [PROFILE_ROW, None, EMPTY_PLAN_ROW, {"id": "existing-log-id"}]
        )

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
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
        sql, _ = _last_sql_and_args(execute_mock)
        assert sql.strip().startswith("UPDATE")

    async def test_update_targets_correct_id(self):
        """UPDATE must be called with the exact existing record id."""
        existing_id = "log-uuid-abc123"
        fetchrow_mock, fetch_mock, execute_mock = _patches(
            [PROFILE_ROW, None, EMPTY_PLAN_ROW, {"id": existing_id}]
        )

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "Уточнённые данные",
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
            })

        _, args = _last_sql_and_args(execute_mock)
        assert args[-1] == existing_id

    async def test_cycle_not_advanced_on_update(self):
        """Cycle must NOT be advanced when UPDATEing an existing record."""
        fake_cycle = {"id": "cycle-001", "current_week": 1, "current_session_index": 0}
        advance_mock = AsyncMock(return_value={"status": "advanced"})

        fetchrow_mock, fetch_mock, execute_mock = _patches(
            [PROFILE_ROW, None, EMPTY_PLAN_ROW, {"id": "existing-id"}]
        )

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=fake_cycle)), \
             patch("agent.tools.workouts.session_log._advance_cycle_position", advance_mock), \
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
        fetchrow_mock, fetch_mock, execute_mock = _patches(
            [PROFILE_ROW, None, EMPTY_PLAN_ROW, {"id": "existing-id"}]
        )

        new_notes = "60кг × 12 повторений, ощущения отличные"

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": new_notes,
                "workout_id": "wid-001",
                "performance": PERFORMANCE_REAL,
                "done_as_planned": False,
            })

        updated_record = _update_record(execute_mock)
        assert updated_record["notes"] == new_notes
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

    async def _call(self, done_as_planned, performance, existing_row=None):
        # done_as_planned=False + workout_id + performance → next_session block
        # also reads the plan, adding one more fetchrow() call before the
        # existing-log check.
        fetchrow_results = [PROFILE_ROW, None]
        if not done_as_planned:
            fetchrow_results.append(EMPTY_PLAN_ROW)
        fetchrow_results.append(existing_row)

        fetchrow_mock, fetch_mock, execute_mock = _patches(fetchrow_results)

        with patch("agent.tools.workouts.session_log._get_user_id", AsyncMock(return_value="uid-1")), \
             patch("agent.tools.workouts.session_log.fetchrow", fetchrow_mock), \
             patch("agent.tools.workouts.session_log.fetch", fetch_mock), \
             patch("agent.tools.workouts.session_log.execute", execute_mock), \
             patch("agent.tools.workouts.session_log._get_active_cycle_data", AsyncMock(return_value=None)), \
             patch("agent.tools.exercise_db.EXERCISE_DB", []):

            from agent.tools.workouts import log_workout
            result = await log_workout.ainvoke({
                "telegram_user_id": 12345,
                "notes": "notes",
                "workout_id": "wid-001",
                "performance": performance,
                "done_as_planned": done_as_planned,
            })

        return result, execute_mock

    async def test_first_call_inserts(self):
        _, execute_mock = await self._call(
            done_as_planned=True,
            performance=PERFORMANCE,
            existing_row=None,  # no existing → INSERT
        )
        sql, _ = _last_sql_and_args(execute_mock)
        assert sql.strip().startswith("INSERT")

    async def test_second_call_updates(self):
        """Second call with real weights finds existing record → UPDATE."""
        _, execute_mock = await self._call(
            done_as_planned=False,
            performance=PERFORMANCE_REAL,
            existing_row={"id": "first-insert-id"},
        )
        sql, _ = _last_sql_and_args(execute_mock)
        assert sql.strip().startswith("UPDATE")

    async def test_second_call_replaces_performance(self):
        """Real performance data must overwrite the plan placeholder."""
        _, execute_mock = await self._call(
            done_as_planned=False,
            performance=PERFORMANCE_REAL,
            existing_row={"id": "first-insert-id"},
        )
        updated_record = _update_record(execute_mock)
        assert updated_record["done_as_planned"] is False
        assert updated_record["performance"][0]["weight_kg"] == 100.0
