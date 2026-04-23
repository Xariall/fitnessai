from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


class UserProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    age: int | None = Field(default=None, ge=10, le=120)
    height: float | None = Field(default=None, gt=50, le=300)
    weight: float | None = Field(default=None, gt=10, le=500)
    gender: str | None = None
    activity: str | None = None
    goal: str | None = None
    injuries: str | None = Field(default=None, max_length=2000)
    # Extended profile fields
    conditions: str | None = Field(default=None, max_length=2000)
    food_allergies: str | None = Field(default=None, max_length=2000)
    meals_per_day: int | None = Field(default=None, ge=1, le=10)
    diet_type: str | None = Field(default=None, max_length=500)
    food_budget: str | None = Field(default=None, max_length=50)
    experience_level: str | None = Field(default=None, max_length=50)
    training_location: str | None = Field(default=None, max_length=500)
    training_days: int | None = Field(default=None, ge=1, le=7)
    session_duration: str | None = Field(default=None, max_length=50)
    training_budget: str | None = Field(default=None, max_length=50)
    onboarding_completed: bool | None = None
    nutrition_unlocked: bool | None = None
    workout_unlocked: bool | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"male", "female", "other", "prefer_not_to_say"}:
            raise ValueError("gender must be male, female, other, or prefer_not_to_say")
        return v

    @field_validator("activity")
    @classmethod
    def validate_activity(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"sedentary", "moderate", "active", "athlete"}:
            raise ValueError("invalid activity level")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"lose", "gain", "maintain", "recomposition", "endurance", "healthy", "athletic"}
        if v not in allowed:
            raise ValueError("invalid goal")
        return v


class OnboardingSubmit(BaseModel):
    """Full onboarding payload — blocks 1+2 required, 3+4 optional."""
    # Block 1 — required
    name: str = Field(min_length=1, max_length=100)
    gender: str
    age: int = Field(ge=14, le=99)
    height: float = Field(gt=50, le=300)
    weight: float = Field(gt=10, le=500)
    goal: str
    # Block 2 — required
    conditions: str = Field(max_length=2000)
    injuries: str = Field(max_length=2000)
    food_allergies: str = Field(max_length=2000)
    # Block 3 — optional
    meals_per_day: int | None = Field(default=None, ge=1, le=10)
    diet_type: str | None = Field(default=None, max_length=500)
    food_budget: str | None = Field(default=None, max_length=50)
    # Block 4 — optional
    experience_level: str | None = Field(default=None, max_length=50)
    training_location: str | None = Field(default=None, max_length=500)
    training_days: int | None = Field(default=None, ge=1, le=7)
    session_duration: str | None = Field(default=None, max_length=50)
    training_budget: str | None = Field(default=None, max_length=50)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if v not in {"male", "female", "prefer_not_to_say"}:
            raise ValueError("invalid gender")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        allowed = {"lose", "gain", "maintain", "recomposition", "endurance", "healthy", "athletic"}
        if v not in allowed:
            raise ValueError("invalid goal")
        return v


class WaitlistSignup(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=255)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


# ── Read schemas (responses) ──────────────────────────────────────────────────

class UserProfile(BaseModel):
    id: int
    email: str | None
    name: str | None
    picture: str | None
    age: int | None
    height: float | None
    weight: float | None
    gender: str | None
    activity: str | None
    goal: str | None
    injuries: str | None
    conditions: str | None
    food_allergies: str | None
    meals_per_day: int | None
    diet_type: str | None
    food_budget: str | None
    experience_level: str | None
    training_location: str | None
    training_days: int | None
    session_duration: str | None
    training_budget: str | None
    onboarding_completed: bool
    nutrition_unlocked: bool
    workout_unlocked: bool


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: int
    role: str          # "user" | "assistant"
    content: str
    created_at: datetime


class ChatResponse(BaseModel):
    response: str
