"""
Training records API endpoints for Telegram Web App.
Provides personal records, exercise progression, weekly volume, and 12-week recap.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.utils.records import (
    get_max_lifts_internal,
    get_exercise_progression,
    get_exercises_list,
    get_weekly_volume,
    get_12week_recap,
)
from api.utils.security import verify_telegram_user
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["records"])


@router.get("/records/{telegram_user_id}")
async def get_records(
    telegram_user_id: int,
    days: int = Query(90, ge=7, le=365),
    tg_user_id: int | None = Depends(verify_telegram_user),
) -> dict:
    """
    GET /api/records/{telegram_user_id}?days=90

    Fetch training records: exercises list, personal records,
    weekly volume, 12-week recap.
    """
    # Security: if initData provided, verify user matches
    if tg_user_id is not None and tg_user_id != telegram_user_id:
        logger.warning(
            "User %d tried to access records of %d",
            tg_user_id, telegram_user_id,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        user_id = await _get_user_id(telegram_user_id)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        exercises = await get_exercises_list(user_id, days)
        personal_records = await get_max_lifts_internal(user_id, telegram_user_id, days)
        weekly_volume = await get_weekly_volume(user_id, telegram_user_id, days)
        recap_12w = await get_12week_recap(user_id, telegram_user_id)

        return {
            "exercises": exercises,
            "personal_records": personal_records,
            "weekly_volume": weekly_volume,
            "recap_12w": recap_12w,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get records for user %s: %s", telegram_user_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Ошибка загрузки данных. Попробуй снова.",
        )


@router.get("/records/{telegram_user_id}/exercise/{exercise_id}")
async def get_exercise_history(
    telegram_user_id: int,
    exercise_id: str,
    days: int = Query(365, ge=7, le=730),
    tg_user_id: int | None = Depends(verify_telegram_user),
) -> list[dict]:
    """
    GET /api/records/{telegram_user_id}/exercise/{exercise_id}?days=365

    Fetch per-session progression for a single exercise.
    Returns ExerciseChartPoint[] (max 50 sessions, ordered ASC).
    """
    if tg_user_id is not None and tg_user_id != telegram_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        user_id = await _get_user_id(telegram_user_id)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        return await get_exercise_progression(
            user_id, telegram_user_id, exercise_id, days
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to get exercise progression for %s/%s: %s",
            telegram_user_id, exercise_id, exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Ошибка загрузки данных.",
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint for deployment verification."""
    return {"status": "ok", "service": "records-api"}
