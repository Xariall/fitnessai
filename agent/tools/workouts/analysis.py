"""Аналитика прогресса: рекорды, история упражнения, roadmap, объём по мышцам."""
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from db.client import fetch, fetchrow
from db.utils import get_user_id as _get_user_id

from ._shared import _INCREMENT_COMPOUND, _INCREMENT_ISOLATION, _calc_1rm, _normalize_key

logger = logging.getLogger(__name__)


def _ema(values: list[float], alpha: float = 0.4) -> list[float]:
    """Экспоненциальное скользящее среднее (EMA) для сглаживания ряда."""
    if not values:
        return []
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


@tool
async def get_current_max_lifts(telegram_user_id: int, limit: int = 10) -> dict:
    """Получить топ-упражнения по текущему максимальному весу (рекорды).

    Возвращает лучшие упражнения по максимальному весу/1RM за последние 90 дней.
    Полезно для быстрого просмотра своих рекордов.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        limit: Максимальное количество упражнений в топе (по умолчанию 10).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"error": "Пользователь не найден."}

    since_90d = datetime.now(timezone.utc) - timedelta(days=90)

    logs = await fetch(
        "SELECT completed_at, performance FROM workout_logs "
        "WHERE user_id = $1 AND completed_at >= $2 ORDER BY completed_at DESC",
        user_id, since_90d,
    )

    if not logs:
        return {
            "message": "Пока нет записанных тренировок. Начни первую — и рекорды заполнятся!",
            "max_lifts": [],
        }

    # Load bodyweight for bodyweight exercise calculations
    profile_row = await fetchrow(
        "SELECT weight_kg FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    user_bodyweight: float | None = (profile_row or {}).get("weight_kg")

    # Load EXERCISE_DB for bodyweight detection
    from agent.tools.exercise_db import EXERCISE_DB
    ex_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Aggregate max weight per exercise
    max_by_exercise: dict[str, dict] = {}
    for log in logs:
        for ex in (log.get("performance") or []):
            if ex.get("is_warmup"):
                continue
            key = ex.get("key") or _normalize_key(ex.get("name", ""))
            name = ex.get("name", key)
            reps = ex.get("reps_done") or 0

            # Calculate effective weight
            effective_w: float | None = None
            w = ex.get("weight_kg")
            db_ex = ex_map.get(key)
            is_bw = db_ex.uses_bodyweight if db_ex else False

            if w is not None and w > 0:
                effective_w = w
            elif is_bw and user_bodyweight:
                effective_w = user_bodyweight + (ex.get("added_kg") or 0)
            elif ex.get("added_kg") and user_bodyweight:
                effective_w = user_bodyweight + ex.get("added_kg")

            # Calculate 1RM
            one_rm: float | None = None
            if effective_w and reps > 0:
                one_rm = _calc_1rm(effective_w, reps)

            # Keep max
            if key not in max_by_exercise:
                max_by_exercise[key] = {
                    "name": name,
                    "weight_kg": w,
                    "reps_done": reps,
                    "effective_weight": effective_w,
                    "estimated_1rm": one_rm,
                    "date": log["completed_at"][:10],
                }
            else:
                current_1rm = max_by_exercise[key].get("estimated_1rm") or 0
                new_1rm = one_rm or 0
                if new_1rm > current_1rm:
                    max_by_exercise[key] = {
                        "name": name,
                        "weight_kg": w,
                        "reps_done": reps,
                        "effective_weight": effective_w,
                        "estimated_1rm": one_rm,
                        "date": log["completed_at"][:10],
                    }

    # Sort by 1RM and return top
    sorted_lifts = sorted(
        max_by_exercise.values(),
        key=lambda x: (x.get("estimated_1rm") or 0),
        reverse=True,
    )[:limit]

    return {
        "max_lifts": [
            {
                "name": lift["name"],
                "max_weight_kg": round(lift["effective_weight"], 1) if lift["effective_weight"] else None,
                "estimated_1rm": round(lift["estimated_1rm"], 1) if lift["estimated_1rm"] else None,
                "reps_at_max": lift["reps_done"],
                "date": lift["date"],
            }
            for lift in sorted_lifts
        ],
        "total_exercises_tracked": len(max_by_exercise),
    }


@tool
async def get_exercise_history(
    telegram_user_id: int,
    exercise_name: str,
    limit: int = 10,
) -> list[dict]:
    """История результатов по конкретному упражнению (вес × повторения по датам).

    Args:
        telegram_user_id: ID пользователя в Telegram.
        exercise_name: Название упражнения (например "Bench Press" или "жим лёжа").
        limit: Максимальное количество записей (по умолчанию 10).
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return [{"error": "Пользователь не найден."}]

    since_90d = datetime.now(timezone.utc) - timedelta(days=90)
    search_key = _normalize_key(exercise_name)

    logs = await fetch(
        "SELECT completed_at, performance FROM workout_logs "
        "WHERE user_id = $1 AND completed_at >= $2 "
        "ORDER BY completed_at DESC LIMIT $3",
        user_id, since_90d, limit * 5,
    )

    # Exact key match first
    history: list[dict] = []
    for log in logs:
        for ex in (log.get("performance") or []):
            if ex.get("key") == search_key:
                history.append({
                    "date": log["completed_at"][:10],
                    "name": ex.get("name"),
                    "weight_kg": ex.get("weight_kg"),
                    "reps_done": ex.get("reps_done"),
                    "sets_done": ex.get("sets_done"),
                })
                break
        if len(history) >= limit:
            break

    # Partial match fallback
    if not history:
        for log in logs:
            for ex in (log.get("performance") or []):
                if search_key in (ex.get("key") or ""):
                    history.append({
                        "date": log["completed_at"][:10],
                        "name": ex.get("name"),
                        "weight_kg": ex.get("weight_kg"),
                        "reps_done": ex.get("reps_done"),
                        "sets_done": ex.get("sets_done"),
                    })
                    break
            if len(history) >= limit:
                break
        names = {e["name"] for e in history if e.get("name")}
        if len(names) > 1:
            return [{"warning": f"Уточни название: найдено {', '.join(sorted(names))}."}]

    if not history:
        return [{"message": f"История по упражнению '{exercise_name}' не найдена за последние 90 дней."}]

    return list(reversed(history))


@tool
async def get_training_roadmap(telegram_user_id: int) -> dict:
    """Дорожная карта прогресса по всем упражнениям за последние 60 дней.

    Показывает историю весов и повторений, тренд прогрессии, и следующую цель для каждого упражнения.

    Args:
        telegram_user_id: ID пользователя в Telegram.
    """
    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"exercises": {}, "total_sessions": 0, "error": "Пользователь не найден."}

    since_60d = datetime.now(timezone.utc) - timedelta(days=60)

    logs = await fetch(
        "SELECT completed_at, performance FROM workout_logs "
        "WHERE user_id = $1 AND completed_at >= $2 ORDER BY completed_at DESC",
        user_id, since_60d,
    )

    if not logs:
        return {
            "exercises": {},
            "total_sessions": 0,
            "message": "Пока нет записей тренировок. Начни первую — и roadmap заполнится!",
        }

    from agent.tools.exercise_db import EXERCISE_DB
    ex_map = {_normalize_key(ex.name): ex for ex in EXERCISE_DB}

    # Load user profile for bodyweight 1RM estimation
    profile_row = await fetchrow(
        "SELECT weight_kg FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    bodyweight_kg: float | None = (profile_row or {}).get("weight_kg")

    # Aggregate per exercise key in chronological order (logs are desc, so reversed)
    key_data: dict[str, list[dict]] = {}
    for log in reversed(logs):
        date = log["completed_at"][:10]
        for ex in (log.get("performance") or []):
            if ex.get("is_warmup"):
                continue
            key = ex.get("key") or _normalize_key(ex.get("name", ""))
            if key not in key_data:
                key_data[key] = []
            key_data[key].append({
                "date": date,
                "name": ex.get("name"),
                "weight_kg": ex.get("weight_kg"),
                "reps_done": ex.get("reps_done"),
                "sets_done": ex.get("sets_done"),
                "rir": ex.get("rir"),
                "added_kg": ex.get("added_kg"),
            })

    exercises: dict = {}
    for key, history_points in key_data.items():
        if not history_points:
            continue

        display_name = history_points[-1].get("name") or key

        # Calculate effective weights (for bodyweight exercises too)
        db_ex = ex_map.get(key)
        is_bodyweight = db_ex.uses_bodyweight if db_ex else False

        effective_weights = []
        for p in history_points:
            w = p.get("weight_kg")
            if w is not None:
                effective_weights.append(w)
            elif is_bodyweight and bodyweight_kg:
                effective_weights.append(bodyweight_kg + (p.get("added_kg") or 0))

        weights = [p["weight_kg"] for p in history_points if p.get("weight_kg") is not None]

        # Calculate trend based on effective_weights (includes bodyweight)
        if len(effective_weights) >= 2:
            delta = round(effective_weights[-1] - effective_weights[0], 2)
            if delta > 0:
                trend = f"↑ +{delta}кг"
            elif delta < 0:
                trend = f"↓ {delta}кг"
            else:
                trend = "→ без изменений"
        elif effective_weights:
            trend = "данных пока мало"
        else:
            trend = "вес не фиксировался"

        next_target = None
        next_target_reps = None
        if weights:
            db_ex = ex_map.get(key)
            is_compound = db_ex.is_compound if db_ex else False
            increment = _INCREMENT_COMPOUND if is_compound else _INCREMENT_ISOLATION
            next_target = round(weights[-1] + increment, 2)
        elif key_data[key]:  # Bodyweight без weight_kg
            # For bodyweight exercises, suggest +2 reps on next session
            last_reps = key_data[key][-1].get("reps_done")
            if last_reps:
                next_target_reps = last_reps + 2

        # ── 1RM + analytics ─────────────────────────────────────────────
        one_rm_series: list[float] = []
        rir_values: list[float] = []

        for p in history_points:
            w = p.get("weight_kg")
            r = p.get("reps_done") or 0
            added = p.get("added_kg")
            rir = p.get("rir")

            if rir is not None:
                rir_values.append(float(rir))

            effective_w: float | None = None
            ex_info = ex_map.get(key)
            is_bw = ex_info.uses_bodyweight if ex_info else False
            if w is not None and w > 0:
                effective_w = w
            elif is_bw and bodyweight_kg:
                effective_w = bodyweight_kg + (added or 0)  # расчётная оценка
            elif added is not None and bodyweight_kg:
                effective_w = bodyweight_kg + added  # fallback

            if effective_w and r > 0:
                one_rm_series.append(_calc_1rm(effective_w, r))

        avg_rir: float | None = round(sum(rir_values) / len(rir_values), 1) if rir_values else None
        estimated_1rm: float | None = round(one_rm_series[-1], 1) if one_rm_series else None
        max_1rm: float | None = round(max(one_rm_series), 1) if one_rm_series else None

        # Plateau detection
        plateau_detected = False
        underload_detected = False
        sessions_since_progress = 0
        trend_score: float | None = None
        trend_label = "insufficient_data"

        if one_rm_series:
            max_idx = one_rm_series.index(max(one_rm_series))
            sessions_since_progress = len(one_rm_series) - 1 - max_idx

            weeks_since_progress = 0.0
            if sessions_since_progress > 0:
                try:
                    last_progress_dt = datetime.fromisoformat(
                        history_points[max_idx]["date"]
                    )
                    latest_dt = datetime.fromisoformat(history_points[-1]["date"])
                    weeks_since_progress = (latest_dt - last_progress_dt).days / 7
                except (ValueError, KeyError):
                    pass

            # Priority: underload first (avg_rir > 3 = not plateau, just too easy)
            if avg_rir is not None and avg_rir > 3:
                underload_detected = True
            else:
                plateau_detected = sessions_since_progress >= 5 or weeks_since_progress >= 3

        # Trend score (requires ≥3 points for EMA)
        if len(one_rm_series) >= 3:
            smoothed = _ema(one_rm_series)
            first_s, last_s = smoothed[0], smoothed[-1]
            delta_pct = ((last_s - first_s) / first_s * 100) if first_s else 0.0

            mid = len(history_points) // 2
            first_sets = sum((p.get("sets_done") or 1) for p in history_points[:mid])
            second_sets = sum((p.get("sets_done") or 1) for p in history_points[mid:])
            vol_delta_pct = ((second_sets - first_sets) / first_sets * 100) if first_sets else 0.0

            rir_modifier = 1.0
            if avg_rir is not None:
                rir_modifier = max(0.0, 1.0 - (avg_rir - 2) * 0.1)

            trend_score = round((delta_pct * 0.7 + vol_delta_pct * 0.3) * rir_modifier, 2)

        # trend_label (mutual exclusive, priority order)
        if underload_detected:
            trend_label = "underload"
        elif plateau_detected:
            trend_label = "plateau"
        elif trend_score is not None:
            if trend_score > 0:
                trend_label = "up"
            elif trend_score < 0:
                trend_label = "down"
            else:
                trend_label = "stable"
        elif len(one_rm_series) >= 2:
            delta_simple = one_rm_series[-1] - one_rm_series[-2]
            trend_label = "up" if delta_simple > 0 else ("down" if delta_simple < 0 else "stable")

        exercises[key] = {
            "display_name": display_name,
            "history": [
                {
                    "date": p["date"],
                    "weight_kg": p.get("weight_kg"),
                    "reps_done": p.get("reps_done"),
                    "rir": p.get("rir"),
                }
                for p in history_points
            ],
            "trend": trend,
            "next_target": next_target,
            "next_target_reps": next_target_reps,  # For bodyweight exercises
            "sessions_count": len(history_points),
            # 1RM analytics
            "estimated_1rm": estimated_1rm,
            "max_1rm": max_1rm,
            "avg_rir": avg_rir,
            # Progression state
            "plateau_detected": plateau_detected,
            "underload_detected": underload_detected,
            "sessions_since_progress": sessions_since_progress,
            # Trend
            "trend_score": trend_score,
            "trend_label": trend_label,
        }

    return {"exercises": exercises, "total_sessions": len(logs)}


@tool
async def get_weekly_volume(telegram_user_id: int, weeks_back: int = 4) -> dict:
    """Объём тренировок по группам мышц за последние N недель.

    Показывает количество сетов и тоннаж (кг) по группам мышц в разрезе ISO-недель.
    Помогает выявить мышцы с дефицитом нагрузки.

    Args:
        telegram_user_id: ID пользователя в Telegram.
        weeks_back: За сколько недель считать (по умолчанию 4).
    """
    from agent.tools.exercise_db import EXERCISE_DB

    user_id = await _get_user_id(telegram_user_id)
    if not user_id:
        return {"weeks": [], "totals": {}, "error": "Пользователь не найден"}

    since = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)

    logs = await fetch(
        "SELECT completed_at, performance FROM workout_logs "
        "WHERE user_id = $1 AND completed_at >= $2 ORDER BY completed_at",
        user_id, since,
    )

    if not logs:
        return {
            "weeks": [],
            "totals": {},
            "message": f"Нет тренировок за последние {weeks_back} недели.",
        }

    # Build exercise maps from EXERCISE_DB
    ex_to_group = {_normalize_key(ex.name): ex.muscle_group for ex in EXERCISE_DB}
    ex_bw_set = {_normalize_key(ex.name) for ex in EXERCISE_DB if ex.uses_bodyweight}

    # Load user bodyweight for bodyweight exercise tonnage
    profile_row = await fetchrow(
        "SELECT weight_kg FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    bodyweight_kg: float = (profile_row or {}).get("weight_kg") or 0.0

    # Aggregate by ISO week and muscle group
    # week_data: {iso_week: {group: {"sets": int, "volume_kg": float}}}
    week_data: dict[str, dict[str, dict]] = {}
    totals: dict[str, dict] = {}

    for log in logs:
        completed = log["completed_at"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(completed)
        iso_week = dt.strftime("%G-W%V")  # e.g. "2026-W22"

        if iso_week not in week_data:
            week_data[iso_week] = {}

        for ex in (log.get("performance") or []):
            if ex.get("is_warmup"):
                continue
            key = ex.get("key") or _normalize_key(ex.get("name", ""))
            group = ex_to_group.get(key, "other")

            sets = ex.get("sets_done") or 1
            reps = ex.get("reps_done") or 0
            raw_weight = ex.get("weight_kg") or 0.0
            added = ex.get("added_kg") or 0.0
            # For bodyweight exercises, use bodyweight as effective weight
            if key in ex_bw_set and raw_weight == 0.0 and bodyweight_kg > 0:
                weight = bodyweight_kg + added
            else:
                weight = raw_weight

            if group not in week_data[iso_week]:
                week_data[iso_week][group] = {"sets": 0, "volume_kg": 0.0}
            week_data[iso_week][group]["sets"] += sets
            week_data[iso_week][group]["volume_kg"] += round(sets * reps * weight, 1)

            if group not in totals:
                totals[group] = {"sets": 0, "volume_kg": 0.0}
            totals[group]["sets"] += sets
            totals[group]["volume_kg"] += round(sets * reps * weight, 1)

    weeks_list = [
        {"iso_week": w, "groups": data}
        for w, data in sorted(week_data.items())
    ]
    return {"weeks": weeks_list, "totals": totals}
