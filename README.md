# FitAgent — AI Фитнес-тренер

Персональный AI фитнес-тренер с поддержкой тренировок, питания и анализа фото еды.

## Стек

- **Gemini 2.0 Flash** — LLM с vision (анализ фото еды)
- **FastAPI** — бэкенд
- **LangGraph** — агент-оркестратор
- **FastMCP** — 2 MCP-сервера (тренировки + питание)
- **SQLite** — база данных
- **HTML/JS** — веб-интерфейс чата

## Быстрый старт

### 1. Установка зависимостей

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
cp .env.example .env
```

Получите бесплатный API ключ: https://aistudio.google.com/apikey

Заполните `.env`:
- `GEMINI_API_KEY` — ключ от Google AI Studio
- `BOT_TOKEN` — токен Telegram бота (из BotFather)
- `DB_PASS` — надёжный пароль для PostgreSQL
- `API_SECRET` — общий секрет для авторизации запросов (опционально, пусто = без авторизации)

### 3. Запуск

```bash
python -m uvicorn api.main:app --reload --port 8000
```

Откройте http://localhost:8000

## Что умеет

| Команда | Пример |
|---------|--------|
| Программа тренировок | «Составь программу на 3 дня для похудения» |
| Запись тренировки | «Запиши тренировку: жим 80кг 3x10» |
| Запись веса | «Мой вес сегодня 78кг» |
| Дневник питания | «Что я ел сегодня?» |
| Запись еды | «Записи: куриная грудка 200г» |
| Анализ фото | Прикрепить фото + указать вес порции |
| Расчёт ИМТ | «Рассчитай мой ИМТ» |
| Норма калорий | «Какая моя дневная норма?» |

## Архитектура

```
Web UI (HTML/JS)
     ↓
FastAPI (/api/chat, /api/chat/image)
     ↓
LangGraph Agent (Gemini 2.0 Flash)
     ↓
┌────────────┐    ┌──────────────┐    ┌──────────────┐
│ fitness_mcp │    │ nutrition_mcp│    │ Custom Tools │
│ (FastMCP)   │    │ (FastMCP)    │    │ (Gemini API) │
└──────┬──────┘    └──────┬───────┘    └──────────────┘
       └──────────┬───────┘
              SQLite DB
```

## MCP-серверы

### fitness_mcp (8 tools)
- `get_exercises` — список упражнений по группе мышц
- `log_workout_entry` — запись тренировки
- `get_workout_logs` — история тренировок
- `log_weight` / `get_weight_history` — вес тела
- `save_program` / `get_programs` — программы
- `get_progress` — сводка прогресса

### nutrition_mcp (6 tools)
- `search_food` — поиск продуктов (57 в базе)
- `log_meal` / `log_meal_from_base` — запись еды
- `get_food_diary` — дневник за день
- `get_daily_summary` — итого КБЖУ
- `calculate_daily_norm` — норма по профилю

### Custom tools (3)
- `analyze_food_photo` — Gemini Vision анализ фото
- `calculate_bmi` — расчёт ИМТ
- `generate_workout_plan` — генерация программы через Gemini

## API

```
POST /api/chat          — текстовый чат
POST /api/chat/image    — чат с фото (multipart/form-data)
POST /api/user          — создание/обновление профиля
GET  /api/user/{id}     — получение профиля
GET  /                  — веб-интерфейс
```
