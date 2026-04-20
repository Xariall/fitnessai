"""Progress API: weight history, workout stats, body metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import get_current_user
from database import db
from database.models import User

router = APIRouter(prefix="/api/progress", tags=["progress"])


class LogWeightBody(BaseModel):
    weight: float = Field(gt=0, lt=500)


@router.get("/summary")
async def get_summary(user: User = Depends(get_current_user)) -> dict:
    uid = str(user.id)
    weight_history = await db.get_weight_history(uid, days=90)
    workout_logs = await db.get_workout_logs(uid)

    current_weight = weight_history[0]["weight"] if weight_history else user.weight
    start_weight = weight_history[-1]["weight"] if len(weight_history) > 1 else None
    weight_change = (
        round(current_weight - start_weight, 1)
        if current_weight is not None and start_weight is not None
        else None
    )

    return {
        "current_weight": current_weight,
        "weight_change_90d": weight_change,
        "total_workouts": len(workout_logs),
        "weight_history": weight_history[:30],  # last 30 entries
        "recent_workouts": workout_logs[:10],
        "profile": {
            "goal": user.goal,
            "height": user.height,
            "activity": user.activity,
        },
    }


@router.post("/weight")
async def log_weight(
    body: LogWeightBody,
    user: User = Depends(get_current_user),
) -> dict:
    await db.log_weight(str(user.id), body.weight)
    return {"success": True, "weight": body.weight}
