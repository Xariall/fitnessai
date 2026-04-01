from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"


class ChatImageRequest(BaseModel):
    message: str
    user_id: str = "default"
    image_base64: str
    weight_grams: float = 300


class UserProfile(BaseModel):
    user_id: str
    name: str | None = None
    age: int | None = None
    height: float | None = None
    weight: float | None = None
    gender: str | None = None
    activity: str | None = None
    goal: str | None = None
