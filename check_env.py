"""
Проверяет что все переменные окружения заданы и зависимости установлены.
Запусти: python check_env.py
"""
import sys


def check_imports() -> list[str]:
    errors = []
    packages = {
        "aiogram": "aiogram",
        "langgraph": "langgraph",
        "langchain_core": "langchain-core",
        "supabase": "supabase",
        "pydantic_settings": "pydantic-settings",
    }
    for module, pkg in packages.items():
        try:
            __import__(module)
        except ImportError:
            errors.append(f"  ✗ {pkg}  →  pip install {pkg}")
    return errors


def check_env() -> list[str]:
    errors = []
    try:
        from config import settings

        required = {
            "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
            "SUPABASE_URL": settings.supabase_url,
            "SUPABASE_SERVICE_KEY": settings.supabase_service_key,
        }
        for name, value in required.items():
            if not value:
                errors.append(f"  ✗ {name} не задан в .env")

        if settings.llm_provider == "gemini" and not settings.gemini_api_key:
            errors.append("  ✗ GEMINI_API_KEY не задан (требуется при LLM_PROVIDER=gemini)")

    except Exception as e:
        errors.append(f"  ✗ Ошибка загрузки config.py: {e}")
    return errors


def main() -> None:
    print("=== FitnessAI — проверка окружения ===\n")

    print("Зависимости:")
    import_errors = check_imports()
    if import_errors:
        for e in import_errors:
            print(e)
    else:
        print("  ✓ Все пакеты установлены")

    print("\nПеременные окружения:")
    env_errors = check_env()
    if env_errors:
        for e in env_errors:
            print(e)
    else:
        from config import settings
        print(f"  ✓ Telegram токен задан")
        print(f"  ✓ Supabase URL: {settings.supabase_url}")
        print(f"  ✓ LLM provider: {settings.llm_provider}")

    all_errors = import_errors + env_errors
    print()
    if all_errors:
        print(f"❌ Найдено проблем: {len(all_errors)}. Исправь и запусти снова.")
        sys.exit(1)
    else:
        print("✅ Всё готово. Запускай бота: python -m bot.main")


if __name__ == "__main__":
    main()
