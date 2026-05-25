from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


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
