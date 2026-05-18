# Daily Changes — Лог изменений

## Для агентов
После каждого изменения кода или базы знаний добавляй запись в этот файл.
Формат: дата → краткое описание → что изменилось (код / БД / база знаний).

---

## 2026-05-15
- Инициализирована база знаний проекта FitnessAI
- Созданы файлы: README.md, context.md, database.md, tools.md, structure.md
- Создан каркас проекта: все папки и базовые файлы по structure.md
- Реализованы все 13 инструментов агента (agent/tools/):
  - profile.py: get_user_profile, update_user_profile
  - workouts.py: generate_workout_plan (LLM), log_workout, get_workout_history, find_exercises (встроенная база)
  - nutrition.py: calculate_daily_calories (формула Миффлина), generate_nutrition_plan (LLM), log_food, get_daily_nutrition_summary, get_food_info (LLM)
  - progress.py: log_progress (с динамикой), get_progress_summary
  - motivation.py: send_motivation (LLM + профиль + прогресс)
- Реализованы: bot/handlers/start.py (FSM онбординга), bot/main.py, llm/provider.py, db/client.py, db/models.py, config.py
- Создана SQL-миграция: migrations/001_initial_schema.sql
  - Таблицы: users, workouts, workout_logs, nutrition_plans, food_logs, progress_logs
  - CHECK-ограничения на goal, activity_level, meal_type
  - Индексы на все user_id и logged_at/measured_at
  - Триггер auto-update updated_at для users
  - RLS включён на всех таблицах, доступ через service_role key
- config.py: добавлен SUPABASE_SERVICE_KEY; db/client.py переключён на service_role
- Исправлены баги перед первым запуском:
  - .gitignore: перезаписан (был сломан heredoc-синтаксом)
  - llm/provider.py: get_llm() обёрнут в @lru_cache — singleton, не пересоздаётся на каждый вызов
  - agent/graph.py: _should_continue теперь ведёт в "responder" вместо END — узел responder больше не мёртвый код
  - agent/graph.py: add_conditional_edges с явным mapping {"tool_executor": ..., "responder": ...}
- Добавлен check_env.py — скрипт проверки зависимостей и .env перед запуском
- Написаны тесты: 87 тестов, все зелёные
  - tests/tools/test_nutrition.py — формула КБЖУ, дневные итоги
  - tests/tools/test_workouts.py — поиск упражнений
  - tests/tools/test_progress.py — дельта веса, сводка за период
  - tests/test_onboarding.py — парсинг цели/активности/веса
  - tests/test_models.py — валидация Pydantic-моделей
  - tests/test_llm_provider.py — фабрика LLM (mock)
- pytest.ini добавлен; pytest + pytest-asyncio + pytest-cov добавлены в requirements.txt

## 2026-05-18

### Память диалога и обработка ошибок
- agent/graph.py: добавлен MemorySaver checkpointer — агент помнит историю диалога в рамках сессии (по thread_id = telegram_user_id)
- agent/state.py: messages переведён на `Annotated[list[BaseMessage], add_messages]` — сообщения накапливаются, а не заменяются
- bot/handlers/chat.py: try/except + parse_mode=MARKDOWN с fallback на plain text
- bot/handlers/start.py: try/except вокруг INSERT в users

### Команда /clear
- bot/handlers/clear.py: удаляет последние 100 сообщений в Telegram-чате через asyncio.gather + TelegramBadRequest per-message fallback

### Фикс Supabase URL
- config.py: field_validator strip_rest_v1 — обрезает /rest/v1/ из SUPABASE_URL если пользователь вставил полный путь

### Системный промпт v2 (agent/prompts/system.py)
- Явное указание telegram_user_id = {telegram_user_id} для всех tool calls
- Точные сценарии с шагами для каждого use case
- Правила Telegram Markdown форматирования с примерами
- Запрет предлагать /log_food — пользователь пишет текстом

### Улучшение плана питания
- generate_nutrition_plan: новый LLM-промпт с реалистичными КБЖУ-якорями (варёная овсянка 100г=88 ккал и др.), новая JSON-схема с items+macros per meal, norms в ответе
- system.py: пример плана с Б/Ж/У per meal и сравнением с нормой

### Улучшение записи еды
- system.py: правило "СРАЗУ вызывай инструменты без уточнений", food_name всегда с граммовкой, стандартные порции (яйцо=55г), запрет показывать "план питания" при записи еды
