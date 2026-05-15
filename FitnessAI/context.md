# Context — Архитектура и ключевые решения

## Концепция
Не просто чат-бот с RAG, а полноценный AI-агент с инструментами и памятью.
Агент сам принимает решения, планирует многошаговые действия и использует инструменты для работы с данными пользователя.

## Архитектура

```
Telegram User
     ↓
aiogram 3 (обработка сообщений)
     ↓
LangGraph Agent (планирование + инструменты)
     ↓
Tools (см. [[tools]])
     ↓
Supabase PostgreSQL (персистентная память)
```

## Стек

| Слой | Технология | Версия |
|------|-----------|--------|
| Telegram | aiogram | 3.x |
| Агент | LangGraph | latest |
| Модель dev | Ollama (qwen2.5:7b) | local |
| Модель prod | Gemini API | gemini-2.0-flash |
| БД | Supabase PostgreSQL | — |
| Язык | Python | 3.11+ |

## Ключевые решения

### Модель
- **Dev:** qwen2.5:7b через Ollama — быстрый, предсказуемый, поддерживает function calling
- **Prod:** Gemini 2.0 Flash — бесплатный tier, быстрый, хорошо следует инструкциям
- Переключение через переменную окружения `LLM_PROVIDER=ollama|gemini`

### Память пользователя
- Профиль хранится в Supabase, идентификатор — `telegram_user_id`
- Регистрация при первом `/start`: имя, возраст, вес, рост, цель, уровень активности
- Агент всегда подгружает профиль перед ответом

### LangGraph
- Агент реализован как граф с узлами: `planner → tool_executor → responder`
- State включает: профиль пользователя, историю сообщений, результаты инструментов
- Checkpointer сохраняет состояние между сообщениями (память сессии)

### Онбординг
- `/start` → проверка регистрации → если новый: онбординг-диалог → сохранение профиля
- Онбординг реализован как отдельный FSM (aiogram States)

## Переменные окружения
```
TELEGRAM_BOT_TOKEN=
SUPABASE_URL=
SUPABASE_KEY=
LLM_PROVIDER=ollama         # ollama | gemini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```
