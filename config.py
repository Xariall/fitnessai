from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str

    database_url: str  # postgres://... — Railway Postgres addon (авто-инжект как DATABASE_URL)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    thinking_budget: int = 8000  # токены на размышление после tool calls (0 = отключено)

    imgflip_username: str = ""
    imgflip_password: str = ""

    # 0 = безлимитно; >0 = максимум запросов к агенту в сутки на пользователя
    max_requests_per_day: int = 0

    # Роутинг по под-агентам (workout/nutrition/progress/motivation/general) вместо
    # одного planner'а со всеми 34 tools сразу. По умолчанию выключено — старый
    # плоский граф остаётся дефолтным путём, пока новый не провалидирован.
    enable_subagent_router: bool = False

    # URL Telegram Web App для рекордов
    web_app_url: str = "https://web-xarialls-projects.vercel.app/records"


settings = Settings()
