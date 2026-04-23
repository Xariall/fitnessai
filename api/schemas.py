from datetime import datetime

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
    onboarding_completed: bool | None = None
    nutrition_unlocked: bool | None = None
    workout_unlocked: bool | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"male", "female", "other"}:
            raise ValueError("gender must be male, female, or other")
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
        if v not in {"lose", "gain", "maintain", "recomposition"}:
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
    onboarding_completed: bool


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
