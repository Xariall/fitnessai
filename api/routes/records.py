"""
Training records API endpoint for Telegram Web App.
Provides max lifts, weekly volume, and 12-week progression data.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.utils.records import (
    get_max_lifts_internal,
    get_weekly_volume,
    get_12week_recap,
)
from db.utils import get_user_id as _get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["records"])


@router.get("/records/{telegram_user_id}")
async def get_records(
    telegram_user_id: int,
    days: int = Query(90, ge=7, le=365),
) -> dict:
    """
    GET /api/records/{telegram_user_id}?days=90

    Fetch training records: max lifts, weekly volume, 12-week recap.

    Returns:
    {
        "max_lifts": [
            {
                "exercise_id": "bench-press",
                "name": "Bench Press",
                "name_ru": "Жим штанги лёжа",
                "weight_kg": 100,
                "reps_done": 5,
                "effective_weight": 100,
                "estimated_1rm": 112.5,
                "date": "2024-06-05"
            },
            ...
        ],
        "weekly_volume": [
            {
                "weekKey": "2024-W23",
                "weekStart": "2024-06-02",
                "byMuscleGroup": {
                    "chest": 15000,
                    "back": 18000,
                    ...
                },
                "total": 50000
            },
            ...
        ],
        "recap_12w": [
            {
                "exercise_id": "squat",
                "exerciseName": "Squat",
                "muscleGroup": "legs",
                "sessions": 12,
                "firstWeight": 100,
                "firstDate": "2024-03-05",
                "lastWeight": 130,
                "lastDate": "2024-06-05",
                "weightDelta": 30,
                "firstE1RM": 112,
                "lastE1RM": 146,
                "e1rmDelta": 34
            },
            ...
        ]
    }
    """
    try:
        user_id = await _get_user_id(telegram_user_id)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        # Fetch all three data sections in parallel-like fashion
        max_lifts = await get_max_lifts_internal(user_id, telegram_user_id, days)
        weekly_volume = await get_weekly_volume(user_id, days)
        recap_12w = await get_12week_recap(user_id)

        return {
            "max_lifts": max_lifts,
            "weekly_volume": weekly_volume,
            "recap_12w": recap_12w,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get records for user %s: %s", telegram_user_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch training records. Please try again.",
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint for deployment verification."""
    return {"status": "ok", "service": "records-api"}
