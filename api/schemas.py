from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[\w\-]+$")


class ChatImageRequest(BaseModel):
    message: str = Field(default="Что это за блюдо?", max_length=500)
    user_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[\w\-]+$")
    image_base64: str
    weight_grams: float = Field(default=300, gt=0, le=5000)


class UserProfile(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w\-]+$")
    name: str | None = Field(default=None, max_length=100)
    age: int | None = Field(default=None, ge=10, le=120)
    height: float | None = Field(default=None, gt=50, le=300)
    weight: float | None = Field(default=None, gt=10, le=500)
    gender: str | None = None
    activity: str | None = None
    goal: str | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"male", "female", "other"}
        if v not in allowed:
            raise ValueError(f"gender must be one of {allowed}")
        return v

    @field_validator("activity")
    @classmethod
    def validate_activity(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"sedentary", "light", "moderate", "active", "very_active"}
        if v not in allowed:
            raise ValueError(f"activity must be one of {allowed}")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"lose", "gain", "maintain", "recomposition"}
        if v not in allowed:
            raise ValueError(f"goal must be one of {allowed}")
        return v
