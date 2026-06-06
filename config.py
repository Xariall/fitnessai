from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str

    supabase_url: str
    supabase_key: str          # anon key
    supabase_service_key: str  # service_role key (только бэкенд)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    thinking_budget: int = 8000  # токены на размышление после tool calls (0 = отключено)

    imgflip_username: str = ""
    imgflip_password: str = ""

    # 0 = безлимитно; >0 = максимум запросов к агенту в сутки на пользователя
    max_requests_per_day: int = 0

    # URL Telegram Web App для рекордов
    web_app_url: str = "https://fitnessai-webapp.vercel.app/records"

    @field_validator("supabase_url")
    @classmethod
    def strip_rest_v1(cls, v: str) -> str:
        """Supabase URL должен быть https://<project>.supabase.co без /rest/v1/."""
        for suffix in ("/rest/v1/", "/rest/v1"):
            if v.endswith(suffix):
                return v[: -len(suffix)]
        return v.rstrip("/")


settings = Settings()
