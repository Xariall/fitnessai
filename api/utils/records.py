"""
Data aggregation helpers for training records API.
Converts Supabase workout logs into charts/tables data.
"""
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.client import get_client
from agent.tools.exercise_db import EXERCISE_DB, get_ru_name
from agent.tools.workouts import _calc_1rm, _MUSCLE_KEYWORDS

logger = logging.getLogger(__name__)


def _normalize_key(name: str) -> str:
    """Canonical exercise key for matching."""
    s = unicodedata.normalize("NFC", name.lower().strip())
    s = s.replace("ё", "е").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _classify_muscle_group(exercise_name: str) -> str:
    """Classify exercise name to muscle group using keyword matching."""
    key = _normalize_key(exercise_name)
    for group, keywords in _MUSCLE_KEYWORDS.items():
        for kw in keywords:
            if kw in key:
                return group
    return "other"


def _iso_week_key(date: datetime) -> str:
    """Return ISO week key in format YYYY-Www."""
    d = date.astimezone(timezone.utc).date()
    # Thursday of the current week (ISO: the week belongs to the year its Thursday falls in)
    day_num = d.weekday()  # Monday=0, Sunday=6
    d = d - timedelta(days=day_num) + timedelta(days=3)
    year_start = datetime(d.year, 1, 1, tzinfo=timezone.utc).date()
    week_no = ((d - year_start).days + 1) // 7 + 1
    return f"{d.year}-W{week_no:02d}"


def _iso_week_start(date: datetime) -> str:
    """Return Monday of the ISO week containing the date (YYYY-MM-DD)."""
    d = date.astimezone(timezone.utc).date()
    day_num = d.weekday()  # Monday=0, Sunday=6
    d = d - timedelta(days=day_num)
    return d.isoformat()


async def get_max_lifts_internal(
    user_id: str,
    telegram_user_id: int,
    days: int = 90,
    limit: int = 10,
) -> list[dict]:
    """
    Get top exercises by estimated 1RM from the last N days.

    Returns list sorted by 1RM descending.
    """
    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Fetch workout logs
    logs_result = (
        await client.table("workout_logs")
        .select("completed_at,performance,cycle_id")
        .eq("user_id", user_id)
        .gte("completed_at", since)
        .order("completed_at", desc=True)
        .execute()
    )
    logs = logs_result.data or []

    # Load user bodyweight
    profile_result = (
        await client.table("users")
        .select("weight_kg")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    user_bodyweight = (profile_result.data or {}).get("weight_kg") or 0

    # Build exercise DB map
    ex_db_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Track max 1RM per exercise
    max_by_exercise: dict[str, dict] = {}

    for log in logs:
        performance = log.get("performance") or []
        completed_at = log.get("completed_at", "")
        date_str = completed_at[:10] if completed_at else ""

        for ex in performance:
            ex_name = ex.get("name") or ""
            ex_key = _normalize_key(ex_name)
            weight_kg = ex.get("weight_kg")
            reps_done = ex.get("reps_done") or 0
            added_kg = ex.get("added_kg") or 0
            is_warmup = ex.get("is_warmup", False)

            if is_warmup or not weight_kg or reps_done <= 0:
                continue

            # Calculate effective weight (for bodyweight exercises)
            ex_db = ex_db_map.get(ex_key)
            if ex_db and ex_db.uses_bodyweight:
                effective_weight = user_bodyweight + added_kg
            else:
                effective_weight = weight_kg

            if effective_weight <= 0:
                continue

            # Calculate 1RM
            e1rm = _calc_1rm(effective_weight, reps_done)
            if e1rm <= 0:
                continue

            # Keep best 1RM for this exercise
            if ex_key not in max_by_exercise:
                max_by_exercise[ex_key] = {
                    "exercise_id": ex_key,
                    "name": ex_name,
                    "name_ru": get_ru_name(ex_name),
                    "weight_kg": weight_kg,
                    "reps_done": reps_done,
                    "effective_weight": round(effective_weight, 1),
                    "estimated_1rm": round(e1rm, 1),
                    "date": date_str,
                    "e1rm_sort": e1rm,
                }
            elif e1rm > max_by_exercise[ex_key].get("e1rm_sort", 0):
                max_by_exercise[ex_key].update({
                    "weight_kg": weight_kg,
                    "reps_done": reps_done,
                    "effective_weight": round(effective_weight, 1),
                    "estimated_1rm": round(e1rm, 1),
                    "date": date_str,
                    "e1rm_sort": e1rm,
                })

    # Sort by 1RM and limit
    result = sorted(
        (v for v in max_by_exercise.values() if "e1rm_sort" in v),
        key=lambda x: x["e1rm_sort"],
        reverse=True,
    )[:limit]

    # Remove temporary sort key
    for r in result:
        r.pop("e1rm_sort", None)

    return result


async def get_weekly_volume(
    user_id: str,
    days: int = 90,
) -> list[dict]:
    """
    Aggregate volume (weight × reps) by muscle group per ISO week.

    Returns list of weeks with byMuscleGroup dict, sorted by week ascending.
    """
    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    logs_result = (
        await client.table("workout_logs")
        .select("completed_at,performance")
        .eq("user_id", user_id)
        .gte("completed_at", since)
        .order("completed_at", asc=True)
        .execute()
    )
    logs = logs_result.data or []

    # Aggregate by week + muscle group
    by_week: dict[str, dict[str, float]] = {}

    for log in logs:
        performance = log.get("performance") or []
        completed_at = log.get("completed_at", "")

        if not completed_at:
            continue

        completed_dt = datetime.fromisoformat(completed_at)
        week_key = _iso_week_key(completed_dt)
        week_start = _iso_week_start(completed_dt)

        if week_key not in by_week:
            by_week[week_key] = {
                "weekKey": week_key,
                "weekStart": week_start,
                "byMuscleGroup": {},
            }

        for ex in performance:
            is_warmup = ex.get("is_warmup", False)
            weight_kg = ex.get("weight_kg")
            reps_done = ex.get("reps_done") or 0

            if is_warmup or not weight_kg or reps_done <= 0:
                continue

            volume = weight_kg * reps_done

            ex_name = ex.get("name") or ""
            muscle_group = _classify_muscle_group(ex_name)

            if muscle_group not in by_week[week_key]["byMuscleGroup"]:
                by_week[week_key]["byMuscleGroup"][muscle_group] = 0

            by_week[week_key]["byMuscleGroup"][muscle_group] += volume

    # Convert to result list with total
    result = []
    for week_data in by_week.values():
        total = sum(week_data["byMuscleGroup"].values())
        result.append({
            "weekKey": week_data["weekKey"],
            "weekStart": week_data["weekStart"],
            "byMuscleGroup": week_data["byMuscleGroup"],
            "total": int(total),
        })

    return sorted(result, key=lambda x: x["weekKey"])


async def get_12week_recap(user_id: str) -> list[dict]:
    """
    Compare first vs last session per exercise over last 12 weeks.

    Returns list of recap rows with session count, load deltas, 1RM deltas.
    """
    client = await get_client()
    since = (datetime.now(timezone.utc) - timedelta(weeks=12)).isoformat()

    logs_result = (
        await client.table("workout_logs")
        .select("completed_at,performance")
        .eq("user_id", user_id)
        .gte("completed_at", since)
        .order("completed_at", asc=True)
        .execute()
    )
    logs = logs_result.data or []

    # Load user bodyweight for 1RM calculation
    profile_result = (
        await client.table("users")
        .select("weight_kg,telegram_user_id")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    user_data = profile_result.data or {}
    user_bodyweight = user_data.get("weight_kg") or 0
    telegram_user_id = user_data.get("telegram_user_id")

    # Build exercise DB map
    ex_db_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Track per exercise: all sessions with max weight per session
    by_exercise: dict[str, list[dict]] = {}

    for log in logs:
        performance = log.get("performance") or []
        completed_at = log.get("completed_at", "")

        if not completed_at:
            continue

        date_str = completed_at[:10]

        for ex in performance:
            ex_name = ex.get("name") or ""
            ex_key = _normalize_key(ex_name)
            weight_kg = ex.get("weight_kg")
            reps_done = ex.get("reps_done") or 0
            added_kg = ex.get("added_kg") or 0
            is_warmup = ex.get("is_warmup", False)

            if is_warmup or not weight_kg or reps_done <= 0:
                continue

            # Calculate effective weight
            ex_db = ex_db_map.get(ex_key)
            if ex_db and ex_db.uses_bodyweight:
                effective_weight = user_bodyweight + added_kg
            else:
                effective_weight = weight_kg

            if effective_weight <= 0:
                continue

            e1rm = _calc_1rm(effective_weight, reps_done)

            if ex_key not in by_exercise:
                by_exercise[ex_key] = {
                    "name": ex_name,
                    "sessions": [],
                }

            by_exercise[ex_key]["sessions"].append({
                "date": date_str,
                "weight": effective_weight,
                "e1rm": e1rm,
            })

    # Build recap rows
    result = []
    for ex_key, ex_data in by_exercise.items():
        sessions = ex_data["sessions"]
        if len(sessions) < 2:
            continue  # Need at least first and last

        first = sessions[0]
        last = sessions[-1]

        result.append({
            "exercise_id": ex_key,
            "exerciseName": ex_data["name"],
            "muscleGroup": _classify_muscle_group(ex_data["name"]),
            "sessions": len(sessions),
            "firstWeight": round(first["weight"], 1),
            "firstDate": first["date"],
            "lastWeight": round(last["weight"], 1),
            "lastDate": last["date"],
            "weightDelta": round(last["weight"] - first["weight"], 1),
            "firstE1RM": round(first["e1rm"], 1),
            "lastE1RM": round(last["e1rm"], 1),
            "e1rmDelta": round(last["e1rm"] - first["e1rm"], 1),
        })

    return sorted(result, key=lambda x: x["exerciseName"])
