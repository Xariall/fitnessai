from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str

    supabase_url: str
    supabase_key: str          # anon key (публичный, для клиентского SDK при необходимости)
    supabase_service_key: str  # service_role key (только бэкенд, никогда не светить)

    llm_provider: str = "ollama"  # ollama | gemini

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"


settings = Settings()
