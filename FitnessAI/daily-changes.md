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
