# Structure — Структура кодовой базы

## Корневая структура

```
fitnessAI_v2/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Точка входа, запуск aiogram
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py         # /start, онбординг FSM
│   │   ├── chat.py          # Основной обработчик сообщений → агент
│   │   └── callbacks.py     # Inline-кнопки
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── main.py          # Клавиатуры и inline-кнопки
│   └── middlewares/
│       ├── __init__.py
│       └── user.py          # Подгрузка профиля пользователя
├── agent/
│   ├── __init__.py
│   ├── graph.py             # LangGraph граф агента
│   ├── state.py             # AgentState (TypedDict)
│   ├── nodes.py             # Узлы графа: planner, executor, responder
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── profile.py       # get_user_profile, update_user_profile
│   │   ├── workouts.py      # generate_workout_plan, log_workout, get_workout_history, find_exercises
│   │   ├── nutrition.py     # calculate_daily_calories, generate_nutrition_plan, log_food, get_daily_nutrition_summary, get_food_info
│   │   ├── progress.py      # log_progress, get_progress_summary
│   │   └── motivation.py    # send_motivation
│   └── prompts/
│       ├── __init__.py
│       └── system.py        # Системный промпт агента
├── db/
│   ├── __init__.py
│   ├── client.py            # Supabase клиент (singleton)
│   └── models.py            # Pydantic модели для таблиц
├── llm/
│   ├── __init__.py
│   └── provider.py          # Фабрика: возвращает Ollama или Gemini в зависимости от LLM_PROVIDER
├── config.py                # Pydantic Settings, загрузка .env
├── .env                     # Переменные окружения (не в git)
├── .env.example             # Пример переменных
├── requirements.txt
├── CLAUDE.md                # Инструкции для Claude Code
└── FitnessAI/               # Obsidian vault (база знаний)
```

## Ключевые файлы

### agent/graph.py
Граф LangGraph. Узлы: `load_profile → planner → tool_executor → responder`.
Checkpointer привязан к `telegram_user_id` для персистентной памяти сессии.

### agent/state.py
```python
class AgentState(TypedDict):
    messages: list
    user_profile: dict
    telegram_user_id: int
```

### llm/provider.py
Фабрика LLM. При `LLM_PROVIDER=ollama` возвращает `ChatOllama`, при `gemini` — `ChatGoogleGenerativeAI`.
Единая точка смены модели без изменения логики агента.

### bot/handlers/start.py
FSM онбординга. Шаги: имя → возраст → вес → рост → цель → уровень активности → сохранение в Supabase.

### bot/middlewares/user.py
Перед каждым сообщением проверяет регистрацию пользователя. Если не зарегистрирован — редиректит на онбординг.
