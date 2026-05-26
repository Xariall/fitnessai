from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class User(BaseModel):
    id: Optional[UUID] = None
    telegram_user_id: int
    name: str
    age: int
    weight_kg: float
    height_cm: float
    goal: str  # lose_weight | gain_muscle | maintain
    activity_level: str  # sedentary | light | moderate | active | very_active
    injuries: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Workout(BaseModel):
    id: Optional[UUID] = None
    user_id: UUID
    title: str
    plan: dict
    created_at: Optional[datetime] = None


class WorkoutLog(BaseModel):
    id: Optional[UUID] = None
    user_id: UUID
    workout_id: Optional[UUID] = None
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    performance: list[dict] = []
    done_as_planned: bool = False
    cycle_id: Optional[UUID] = None
    cycle_week: Optional[int] = None
    cycle_session_index: Optional[int] = None


class NutritionPlan(BaseModel):
    id: Optional[UUID] = None
    user_id: UUID
    target_calories: int
    target_protein: float
    target_fat: float
    target_carbs: float
    plan: dict
    created_at: Optional[datetime] = None


class FoodLog(BaseModel):
    id: Optional[UUID] = None
    user_id: UUID
    food_name: str
    calories: int
    protein: float
    fat: float
    carbs: float
    meal_type: str  # breakfast | lunch | dinner | snack
    logged_at: Optional[datetime] = None


class ProgressLog(BaseModel):
    id: Optional[UUID] = None
    user_id: UUID
    weight_kg: float
    notes: Optional[str] = None
    measured_at: Optional[datetime] = None


# ── Training Cycle models ──────────────────────────────────────────────────────

class TrainingCycleSession(BaseModel):
    session_index: int
    focus: str
    label: str


class TrainingCycleWeek(BaseModel):
    week_number: int
    theme: str
    phase: Literal["accumulation", "intensification", "deload"]
    sessions: list[TrainingCycleSession]


class TrainingCycleSchedule(BaseModel):
    weeks: list[TrainingCycleWeek]

    @model_validator(mode="after")
    def validate_session_counts(self) -> "TrainingCycleSchedule":
        counts = {len(w.sessions) for w in self.weeks}
        if len(counts) > 1:
            raise ValueError("Все недели должны содержать одинаковое количество сессий")
        return self


class TrainingCycle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    user_id: UUID
    title: str
    goal: str
    total_weeks: int
    sessions_per_week: int = 3
    training_type: Optional[str] = None  # strength | hypertrophy | functional | mixed
    equipment: Optional[str] = None       # gym | home_dumbbells | bodyweight
    schedule: TrainingCycleSchedule
    current_week: int = 1
    current_session_index: int = 0
    total_sessions_done: int = 0
    status: str = "active"  # active | completed | paused
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
