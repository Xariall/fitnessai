# CLAUDE.md — Инструкции для агента

## Роль
Ты — Senior Python Developer, работающий над проектом FitnessAI.
FitnessAI — это Telegram-бот с AI-агентом для персонального фитнес-коучинга.
Агент помнит пользователя, составляет планы тренировок и питания, считает КБЖУ, отслеживает прогресс.

## База знаний
У тебя есть доступ к Obsidian vault через MCP (сервер: obsidian).
При получении любой задачи **первым делом читай README.md** из vault, затем переходи по ссылкам к нужному разделу.

### Разделы vault
- **README.md** — точка входа, обзор проекта
- **context.md** — архитектура, стек, ключевые решения
- **database.md** — схема БД, все таблицы и колонки
- **tools.md** — инструменты агента, сигнатуры
- **structure.md** — структура кодовой базы по файлам
- **daily-changes.md** — лог изменений

## Алгоритм работы с задачей

1. Прочитай README.md в Obsidian
2. Найди и прочитай разделы, релевантные задаче
3. Изучи существующий код в проекте если нужно
4. Реализуй задачу, следуя архитектуре из базы знаний
5. Обнови соответствующие файлы в Obsidian (structure, database, tools — если менялись)
6. Запиши изменения в daily-changes.md

## Стек и соглашения

### Технологии
- Python 3.11+
- aiogram 3.x (Telegram)
- LangGraph (агент)
- Supabase (PostgreSQL)
- Ollama qwen2.5:7b (dev) / Gemini 2.0 Flash (prod)

### Переключение модели
Через переменную окружения `LLM_PROVIDER=ollama|gemini`.
Логика в `llm/provider.py` — не дублируй её в других местах.

### Стиль кода
- Type hints везде
- Pydantic для валидации данных и настроек
- Async/await (aiogram и supabase клиент асинхронные)
- Логирование через `logging` (не print)
- Конфиги только через `config.py` (Pydantic Settings), не хардкодить

### Структура инструментов агента
Каждый инструмент — отдельная функция с декоратором `@tool` в соответствующем файле в `agent/tools/`.
Новые инструменты добавляй туда же и регистрируй в `agent/graph.py`.

### База данных
Все запросы к Supabase — через клиент в `db/client.py`.
Модели таблиц — в `db/models.py` (Pydantic).
При изменении схемы БД обязательно обновляй `database.md` в Obsidian.

## Примеры задач

### Пример 1: добавить новый инструмент
Задача: "Добавь инструмент для получения рекомендаций по восстановлению после тренировки"

Твои действия:
1. Читаю README.md → tools.md → structure.md в Obsidian
2. Создаю функцию `get_recovery_tips` в `agent/tools/workouts.py`
3. Регистрирую инструмент в `agent/graph.py`
4. Добавляю описание инструмента в `tools.md` в Obsidian
5. Записываю в `daily-changes.md`

### Пример 2: изменить схему БД
Задача: "Добавь поле body_fat_percent в таблицу progress_logs"

Твои действия:
1. Читаю README.md → database.md в Obsidian
2. Добавляю колонку в Supabase (SQL миграция)
3. Обновляю Pydantic модель в `db/models.py`
4. Обновляю `database.md` в Obsidian
5. Записываю в `daily-changes.md`

### Пример 3: новая фича в боте
Задача: "Добавь команду /stats которая показывает статистику пользователя"

Твои действия:
1. Читаю README.md → structure.md → tools.md в Obsidian
2. Создаю handler в `bot/handlers/`
3. Использую существующие инструменты агента (get_progress_summary, get_daily_nutrition_summary)
4. Регистрирую handler в `bot/main.py`
5. Обновляю `structure.md` в Obsidian
6. Записываю в `daily-changes.md`

## Важно
- Не изменяй архитектурные решения без явного запроса — они описаны в context.md
- Если задача противоречит текущей архитектуре — сообщи об этом и предложи решение
- Всегда проверяй существующий код перед написанием нового — не дублируй логику
- Obsidian — источник истины о проекте, держи его актуальным

## Obsidian MCP
Vault name: **fitnessai** (строчными буквами).
При обращении к Obsidian MCP всегда используй vault `fitnessai`, не `FitnessAI`.

## MCP Telegram уведомления
При завершении задачи **всегда используй `telegram_notify_with_actions`** (не `telegram_notify`).
Стандартный набор кнопок:
```
actions=[
    {"text": "Продолжить", "action": "продолжай со следующей задачей", "emoji": "▶️"},
    {"text": "Покажи diff", "action": "покажи что изменилось (git diff)", "emoji": "🔍"},
    {"text": "Зафиксируй коммит", "action": "создай git коммит с изменениями", "emoji": "✅"},
]
```
Адаптируй кнопки под контекст задачи — предлагай логичные следующие шаги.

# AI Agents — База знаний

Дистиллят из 6 статей по проектированию и построению AI-агентов.
Используй этот файл как справочник при работе над любым агентным проектом.

---

## 1. Когда вообще нужен агент?

Источник: [Arize — How to Build an AI Agent](https://arize.com/blog/how-to-build-an-ai-agent/)

Прежде чем писать код, задай себе три вопроса:

- **Iterative flow**: каждый шаг зависит от результата предыдущего?
- **Adaptive logic**: логика меняется в зависимости от промежуточных результатов?
- **Complex state**: действий больше одного и они не фиксированы?

Если хотя бы одно «да» — агент оправдан. Для простых запросов достаточно одного LLM-вызова.

**Что агент даёт сверх обычного LLM:**
- Memory & Planning — помнит шаги, строит план
- Tool Access — API, веб, БД
- Longevity — улучшается итеративно через feedback

---

## 2. Ключевые характеристики AI-агента

Источник: [GMI Cloud — Vision and Planning](https://www.gmicloud.ai/en/blog/how-to-build-an-ai-agent---part-1-vision-and-planning)

| Характеристика | Описание |
|---|---|
| Perception | Получает данные — API, sensors, knowledge base |
| Processing/Decision | Применяет модели или правила к входным данным |
| Memory | Хранит историю взаимодействий для будущих решений |
| Action | Выполняет действия: отвечает, автоматизирует, вызывает системы |
| Autonomy | Работает без постоянного вмешательства человека |
| Adaptability | Обучается от взаимодействий |

---

## 3. Function Calling: от одного вызова к полному агенту

Источник: [Arize](https://arize.com/blog/how-to-build-an-ai-agent/)

**Single LLM Call with Function Calling:**
- LLM получает список функций и выбирает нужную
- Лучше для простых задач, быстро реализуется
- Результат в JSON, легко парсить

**Full Agent (Multi-Step):**
- Итеративное рассуждение + использование инструментов
- Поддерживает стабильное состояние между вызовами
- Оркестрирует сложные потоки

```python
# Пример: ReAct агент через LangGraph
from langgraph.prebuilt import create_react_agent
from langchain_community.tools.tavily_search import TavilySearchResults

llm = ChatOpenAI(model="o3-mini")
tools = [TavilySearchResults(max_results=10)]
agent = create_react_agent(llm, tools, state_modifier=system_prompt)
```

---

## 4. Архитектура: Plan → Execute → Replan

Источник: [Galileo — Deep Research Agent](https://galileo.ai/blog/deep-research-agent)

Паттерн для исследовательских агентов:

```
Вопрос → Planner → [шаги] → ReAct executor → Replanner → ... → Ответ
```

**State management** — три слоя состояния:
```python
class PlanExecute(TypedDict):
    input: str              # исходный вопрос
    plan: List[str]         # список шагов
    past_steps: Annotated[List[Tuple], operator.add]  # история + результаты
    response: str           # финальный ответ
```

**Плanner** — использует structured output (Pydantic) для получения чёткого списка шагов:
```python
class Plan(BaseModel):
    steps: List[str] = Field(description="шаги в порядке выполнения")
```

**Replanner** — анализирует `past_steps` и корректирует оставшийся план. Это ключевое отличие от простой цепочки — агент адаптируется на ходу.

**Стек для этого паттерна:**
```
pip install langgraph langchain-community langchain-openai tavily-python
```

---

## 5. Компоненты агента (минимальный набор)

Источник: [Apify — How to Build an AI Agent](https://blog.apify.com/how-to-build-an-ai-agent/)

Пять необходимых элементов:

1. **Good prompts** — направляют поведение агента
2. **Powerful tools** — взаимодействие с внешним миром
3. **Strong LLM** — обрабатывает и связывает всё вместе
4. **Agentic framework** — обработка edge-cases, когда LLM ведёт себя непредсказуемо
5. **Platform** — запуск, масштабирование, публичный доступ

---

## 6. Фазы разработки агента

Источник: [GMI Cloud](https://www.gmicloud.ai/en/blog/how-to-build-an-ai-agent---part-1-vision-and-planning)

| Фаза | Фокус | Зачем |
|---|---|---|
| Vision | Определить проблему и ценность | Alignment с бизнес-целями |
| Planning | Scope MVP, определить use-case | Снизить риски, не перестроить |
| Requirements | Данные, модели, инструменты, инфра | Фундамент для технического успеха |
| Challenges | Данные, сложность, стоимость, точность | Предвидеть препятствия заранее |

**Ключевой принцип при выборе идеи:** предпочти идею с доступными данными и понятными метриками успеха. Сложная multimodal задача (например, image → outfit search) может выглядеть просто, но требует на порядок больше усилий.

---

## 7. Оркестрация через Conductor (agentic workflows)

Источник: [Orkes — Agentic Interview App](https://orkes.io/blog/building-agentic-interview-app-with-conductor/)

**Orkes Conductor** — платформа для оркестрации сложных multi-step агентных workflows. Подходит для:
- Human-in-the-loop workflows (вставка человека в процесс)
- Event-driven архитектур
- Долгоживущих процессов (long-running workflows)
- Compliance-чувствительных пайплайнов

**Типичный agentic workflow для интервью:**
```
Ввод кандидата → LLM генерирует вопросы → Оценка ответов → Feedback
```

Conductor даёт визуализацию end-to-end процессов и мониторинг в реальном времени — важно для production агентов.

---

## 8. Test-Time Compute и обучение без разметки (TAO)

Источник: [Databricks — TAO](https://www.databricks.com/blog/tao-using-test-time-compute-train-efficient-llms-without-labeled-data)

**TAO (Test-time compute Assisted Optimization)** — подход Databricks для обучения эффективных LLM без размеченных данных:
- Использует compute во время инференса для генерации обучающих сигналов
- Устраняет bottleneck с ручной разметкой
- Полезно для domain-specific тюнинга без дорогостоящих датасетов

Актуально для AI-инженеров, которые хотят файн-тюнить модели под свои задачи с минимальными ресурсами.

---

## 9. Фреймворки: краткое сравнение

Источник: [Arize](https://arize.com/blog/how-to-build-an-ai-agent/)

| Фреймворк | Когда использовать |
|---|---|
| **LangGraph** | Сложные stateful агенты, циклы, ветвления, graph-based workflow |
| **smolagents** (HuggingFace) | Лёгкие агенты, open-source модели |
| **AutoGen** (Microsoft) | Multi-agent разговоры, агенты-коллеги |
| **CrewAI** | Команды агентов с чёткими ролями |
| **Orkes Conductor** | Enterprise orchestration, compliance, long-running workflows |

---

## 10. Эвалюация агентов

Источник: [Galileo](https://galileo.ai/blog/deep-research-agent)

Важно не только построить агента, но и оценить его качество. Galileo рекомендует:

- Использовать **отдельную модель для оценки** (в примере: o3-mini для генерации, 4o для eval)
- Трекать `past_steps` — история + результаты каждого шага
- Иметь **agent leaderboard** для сравнения моделей как orchestrator

```python
# Используй promptquality для eval pipeline
pip install promptquality
```

---

## Быстрый чеклист при старте агентного проекта

- [ ] Нужен ли вообще агент, или хватит простого LLM-вызова?
- [ ] Определил проблему, пользователей, метрики успеха?
- [ ] Выбрал фреймворк под свои требования?
- [ ] Определил state management (что хранить между шагами)?
- [ ] Спланировал инструменты (tools) агента?
- [ ] Предусмотрел replanning при отклонении от плана?
- [ ] Есть ли eval pipeline для оценки качества?
- [ ] Думал о платформе для деплоя и масштабирования?

---

## Источники

1. [Galileo — Build and Evaluate a Deep Research Agent](https://galileo.ai/blog/deep-research-agent)
2. [Arize — How to Build an AI Agent](https://arize.com/blog/how-to-build-an-ai-agent/)
3. [Databricks — TAO: Test-Time Compute for LLMs](https://www.databricks.com/blog/tao-using-test-time-compute-train-efficient-llms-without-labeled-data)
4. [Apify — How to Build and Monetize an AI Agent](https://blog.apify.com/how-to-build-an-ai-agent/)
5. [GMI Cloud — AI Agent: Vision and Planning (Part 1)](https://www.gmicloud.ai/en/blog/how-to-build-an-ai-agent---part-1-vision-and-planning)
6. [Orkes — Building an Agentic Interview App with Conductor](https://orkes.io/blog/building-agentic-interview-app-with-conductor/)