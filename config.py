from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str

    supabase_url: str
    supabase_key: str          # anon key
    supabase_service_key: str  # service_role key (только бэкенд)

    llm_provider: str = "ollama"  # ollama | gemini

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    @field_validator("supabase_url")
    @classmethod
    def strip_rest_v1(cls, v: str) -> str:
        """Supabase URL должен быть https://<project>.supabase.co без /rest/v1/."""
        for suffix in ("/rest/v1/", "/rest/v1"):
            if v.endswith(suffix):
                return v[: -len(suffix)]
        return v.rstrip("/")


settings = Settings()
