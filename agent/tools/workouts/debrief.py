"""Еженедельный агрегированный разбор тренировок (сравнение недель, алерты, тренды)."""
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from db.client import fetch, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _calc_1rm, _normalize_key

logger = logging.getLogger(__name__)


@tool
async def generate_weekly_debrief(telegram_user_id: int) -> dict:
    """Агрегированный анализ тренировок за текущую vs прошлую неделю.

    Возвращает сравнение объёмов, прогресс по упражнениям (1RM, trend),
    алерты (плато, недогруз, снижение нагрузки) и инфо об активном цикле.
    Используй для еженедельного разбора тренировок.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    from agent.tools.exercise_db import EXERCISE_DB

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден"}

    # ── Profile ───────────────────────────────────────────────────────
    profile = await fetchrow(
        "SELECT weight_kg, goal, activity_level FROM users WHERE telegram_user_id = $1",
        telegram_user_id,
    ) or {}
    bodyweight_kg: float | None = profile.get("weight_kg")

    # ── ISO weeks ─────────────────────────────────────────────────────
    today = datetime.now(timezone.utc)
    current_iso = today.strftime("%G-W%V")
    prev_date = today - timedelta(days=7)
    previous_iso = prev_date.strftime("%G-W%V")

    since = today - timedelta(days=56)  # 8 weeks for exercise trend

    # ── Workout logs (8 weeks) ────────────────────────────────────────
    logs = await fetch(
        "SELECT completed_at, performance FROM workout_logs "
        "WHERE user_id = $1 AND completed_at >= $2 ORDER BY completed_at",
        user_id, since,
    )

    if not logs:
        return {
            "profile_summary": {
                "weight_kg": bodyweight_kg,
                "goal": profile.get("goal"),
            },
            "current_week": {"iso_week": current_iso, "sessions_count": 0},
            "previous_week": {"iso_week": previous_iso, "sessions_count": 0},
            "exercise_comparison": [],
            "volume_by_group": {},
            "alerts": [],
            "active_cycle": None,
            "message": "Нет тренировок за последние 8 недель.",
        }

    # ── Active cycle ──────────────────────────────────────────────────
    active_cycle_data = await fetchrow(
        "SELECT title, current_week, total_weeks, goal, schedule FROM training_cycles "
        "WHERE user_id = $1 AND status = 'active' LIMIT 1",
        user_id,
    )
    active_cycle: dict | None = None
    if active_cycle_data:
        # Determine phase from schedule
        cw = active_cycle_data.get("current_week") or 1
        schedule = active_cycle_data.get("schedule") or {}
        weeks_list = schedule.get("weeks") or []
        phase = "unknown"
        for wk in weeks_list:
            if wk.get("week_number") == cw:
                phase = wk.get("phase", "unknown")
                break
        active_cycle = {
            "title": active_cycle_data.get("title"),
            "week": cw,
            "total_weeks": active_cycle_data.get("total_weeks"),
            "phase": phase,
        }

    # ── Split logs by ISO week ────────────────────────────────────────
    current_logs: list[dict] = []
    previous_logs: list[dict] = []
    for log in logs:
        completed = log["completed_at"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(completed)
        iso = dt.strftime("%G-W%V")
        if iso == current_iso:
            current_logs.append(log)
        elif iso == previous_iso:
            previous_logs.append(log)

    # ── Exercise maps ─────────────────────────────────────────────────
    ex_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}
    ex_to_group = {_normalize_key(ex.name): ex.muscle_group for ex in EXERCISE_DB}

    def _extract_exercises(week_logs: list[dict]) -> dict[str, list[dict]]:
        """Group working-set performance entries by normalized key."""
        result: dict[str, list[dict]] = {}
        for log in week_logs:
            for ex in (log.get("performance") or []):
                if ex.get("is_warmup"):
                    continue
                key = ex.get("key") or _normalize_key(ex.get("name", ""))
                result.setdefault(key, []).append(ex)
        return result

    curr_exercises = _extract_exercises(current_logs)
    prev_exercises = _extract_exercises(previous_logs)

    # ── Per-exercise comparison ───────────────────────────────────────
    all_keys = sorted(set(curr_exercises.keys()) | set(prev_exercises.keys()))
    # Limit to top 15 by total appearances
    key_counts = {k: len(curr_exercises.get(k, [])) + len(prev_exercises.get(k, [])) for k in all_keys}
    top_keys = sorted(all_keys, key=lambda k: key_counts[k], reverse=True)[:15]

    exercise_comparison: list[dict] = []
    alerts: list[str] = []

    for key in top_keys:
        curr_entries = curr_exercises.get(key, [])
        prev_entries = prev_exercises.get(key, [])
        ex_name = (curr_entries or prev_entries)[0].get("name", key)
        db_ex = ex_map.get(key)
        is_bw = db_ex.uses_bodyweight if db_ex else False

        def _best_1rm(entries: list[dict]) -> float | None:
            best = 0.0
            for e in entries:
                w = e.get("weight_kg")
                r = e.get("reps_done") or 0
                added = e.get("added_kg") or 0
                eff_w: float | None = None
                if w is not None and w > 0:
                    eff_w = w
                elif is_bw and bodyweight_kg:
                    eff_w = bodyweight_kg + added
                if eff_w and r > 0:
                    rm = _calc_1rm(eff_w, r)
                    if rm > best:
                        best = rm
            return round(best, 1) if best > 0 else None

        current_1rm = _best_1rm(curr_entries)
        previous_1rm = _best_1rm(prev_entries)

        # RIR
        rir_vals = [float(e["rir"]) for e in curr_entries if e.get("rir") is not None]
        avg_rir = round(sum(rir_vals) / len(rir_vals), 1) if rir_vals else None

        # Delta
        delta_pct: float | None = None
        if current_1rm and previous_1rm and previous_1rm > 0:
            delta_pct = round((current_1rm - previous_1rm) / previous_1rm * 100, 1)

        # Trend
        trend = "stable"
        if avg_rir is not None and avg_rir > 3:
            trend = "underload"
            alerts.append(f"underload: {ex_name} (avg RIR {avg_rir})")
        elif delta_pct is not None:
            if delta_pct > 1:
                trend = "up"
            elif delta_pct < -5:
                trend = "down"
                alerts.append(f"regression: {ex_name} ({delta_pct:+.1f}% 1RM)")
        elif current_1rm is None and previous_1rm is not None:
            trend = "skipped"

        # Sessions since progress (simple: check if current > previous)
        sessions_since = 0
        if current_1rm and previous_1rm and current_1rm <= previous_1rm:
            sessions_since = len(curr_entries)
            if sessions_since >= 5:
                trend = "plateau"
                alerts.append(f"plateau: {ex_name} ({sessions_since} сессий без прогресса)")

        exercise_comparison.append({
            "name": ex_name,
            "current_1rm": current_1rm,
            "previous_1rm": previous_1rm,
            "delta_pct": delta_pct,
            "trend": trend,
            "avg_rir": avg_rir,
            "sessions_since_progress": sessions_since,
        })

    # ── Volume by muscle group ────────────────────────────────────────
    def _volume_by_group(week_logs: list[dict]) -> dict[str, int]:
        groups: dict[str, int] = {}
        for log in week_logs:
            for ex in (log.get("performance") or []):
                if ex.get("is_warmup"):
                    continue
                key = ex.get("key") or _normalize_key(ex.get("name", ""))
                group = ex_to_group.get(key, "other")
                sets = ex.get("sets_done") or 1
                groups[group] = groups.get(group, 0) + sets
        return groups

    curr_vol = _volume_by_group(current_logs)
    prev_vol = _volume_by_group(previous_logs)
    all_groups = sorted(set(curr_vol.keys()) | set(prev_vol.keys()))

    volume_by_group: dict[str, dict] = {}
    for g in all_groups:
        c = curr_vol.get(g, 0)
        p = prev_vol.get(g, 0)
        d = round((c - p) / p * 100, 1) if p > 0 else (100.0 if c > 0 else 0)
        volume_by_group[g] = {"current_sets": c, "previous_sets": p, "delta_pct": d}

    # ── Week summaries ────────────────────────────────────────────────
    def _week_summary(week_logs: list[dict], iso: str) -> dict:
        total_vol = 0.0
        ex_keys: set[str] = set()
        for log in week_logs:
            for ex in (log.get("performance") or []):
                if ex.get("is_warmup"):
                    continue
                key = ex.get("key") or _normalize_key(ex.get("name", ""))
                ex_keys.add(key)
                sets = ex.get("sets_done") or 1
                reps = ex.get("reps_done") or 0
                w = ex.get("weight_kg") or 0.0
                if w == 0 and key in {_normalize_key(e.name) for e in EXERCISE_DB if e.uses_bodyweight} and bodyweight_kg:
                    w = bodyweight_kg + (ex.get("added_kg") or 0)
                total_vol += sets * reps * w
        return {
            "iso_week": iso,
            "sessions_count": len(week_logs),
            "total_volume_kg": round(total_vol, 1),
            "exercises_trained": len(ex_keys),
        }

    return {
        "profile_summary": {
            "weight_kg": bodyweight_kg,
            "goal": profile.get("goal"),
        },
        "current_week": _week_summary(current_logs, current_iso),
        "previous_week": _week_summary(previous_logs, previous_iso),
        "exercise_comparison": exercise_comparison,
        "volume_by_group": volume_by_group,
        "alerts": alerts,
        "active_cycle": active_cycle,
    }
