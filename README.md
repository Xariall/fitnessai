# FitnessAI

Telegram-бот с AI-агентом для персонального фитнес-коучинга. Агент помнит
пользователя, составляет планы тренировок и питания, считает КБЖУ, отслеживает
прогресс и мотивирует — всё через обычную переписку, без слэш-команд для
основных сценариев.

Живой бот: [@voidFitbot](https://t.me/voidFitbot).

## Возможности

- **Тренировки** — генерация разовых планов и многонедельных тренировочных
  циклов с периодизацией, учёт травм/противопоказаний, восстановление между
  сессиями, замена упражнений, недельный разбор нагрузки.
- **Питание** — расчёт КБЖУ (формула Миффлина-Сан Жеора), генерация плана
  питания на день с учётом уже съеденного, запись приёмов пищи текстом,
  протокол питания вокруг тренировки, гидратация. Перед первым планом питания
  агент уточняет у пользователя, какие продукты обычно есть дома, вкусы и
  бюджет — план собирается из реалистичных для Казахстана продуктов, без
  западной экзотики.
- **Прогресс** — замеры веса, динамика, недельные и месячные сводки.
- **Мотивация** — поддержка и генерация мотивационных мемов.
- **Веб-миниаппа рекордов** — отдельный Telegram Web App для просмотра личных
  рекордов по упражнениям (`web/`, FastAPI-бэкенд в `api/`).

## Стек

- **Python 3.12**, [aiogram 3](https://docs.aiogram.dev/) — Telegram-бот
- **LangGraph** — оркестрация AI-агента (граф `load_profile → planner ⇄
  tool_executor → responder`, персистентная память диалога через
  `MemorySaver` + pickle-снапшот)
- **Gemini** (`langchain-google-genai`) — LLM-провайдер: два инстанса,
  быстрый без thinking для планирования и с thinking-бюджетом для синтеза
  ответа после вызова инструментов (`llm/provider.py`)
- **PostgreSQL** напрямую через `asyncpg` (без ORM) — задеплоена как Railway
  Postgres addon
- **FastAPI** (`api/`) — бэкенд для веб-миниаппы рекордов
- **Next.js** (`web/`) — фронтенд веб-миниаппы

Экспериментальный sub-agent router (маршрутизация запроса по 5 доменам —
workout/nutrition/progress/motivation/general — вместо одного planner'а со
всеми инструментами сразу) реализован в `agent/router.py`, но выключен по
умолчанию (`ENABLE_SUBAGENT_ROUTER=false`) — подробности в
[`docs/subagent-router-refactor.md`](docs/subagent-router-refactor.md).

## Структура

```
agent/            LangGraph-агент: граф, узлы, промпты, инструменты (agent/tools/)
bot/              aiogram-бот: handlers, keyboards, middlewares, scheduler, helpers
api/              FastAPI-бэкенд веб-миниаппы рекордов
web/              Next.js-фронтенд веб-миниаппы рекордов
db/               db/client.py (fetch/fetchrow/execute поверх asyncpg.Pool), db/models.py (Pydantic)
llm/              LLM-провайдер (Gemini)
migrations/       001_schema.sql — единый файл схемы, описывает конечное состояние БД
docs/             Документация проекта (архитектура, БД, деплой, use cases, лог изменений)
tests/            pytest — unit-тесты инструментов агента, роутера, API, scheduler
```

## Разработка

### Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN, DATABASE_URL, GEMINI_API_KEY
```

Применить схему БД к пустой Postgres:

```bash
psql "$DATABASE_URL" -f migrations/001_schema.sql
```

### Запуск бота локально

```bash
python -m bot.main
```

### Тесты

```bash
source .venv/bin/activate && pytest
```

Системный `python` (вне `.venv`) не видит `asyncpg` и другие зависимости —
тесты, трогающие `db/client.py`, нужно гонять только через `.venv`.

## Деплой

Продакшен — Railway, проект `fitnessai`: сервисы `bot` (aiogram polling),
`api` (FastAPI, `Dockerfile.api`) и Postgres addon. Сервисы **не подключены**
к GitHub — автодеплоя по `git push` нет, выкладка вручную:

```bash
railway up -s bot --ci --detach
railway up -s api --ci --detach
```

Подробности инфраструктуры, известные особенности и переменные окружения —
[`docs/deployment.md`](docs/deployment.md).

## Документация

| Файл | Содержание |
|------|------------|
| [`docs/database.md`](docs/database.md) | Схема БД, `db/client.py`, грабли asyncpg |
| [`docs/deployment.md`](docs/deployment.md) | Railway-инфраструктура, переменные окружения |
| [`docs/use_cases.md`](docs/use_cases.md) | Use cases по тренировкам и питанию |
| [`docs/subagent-router-refactor.md`](docs/subagent-router-refactor.md) | Sub-agent router (за флагом) |
| [`docs/daily-changes.md`](docs/daily-changes.md) | Лог изменений по дням |
| [`CLAUDE.md`](CLAUDE.md) | Инструкции для AI-агента, работающего над проектом |
