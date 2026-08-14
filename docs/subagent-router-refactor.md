# Sub-agent Router — рефакторинг агента (2026-08-14)

Статус: **готово, за флагом `ENABLE_SUBAGENT_ROUTER` (по умолчанию `false`)**.
Ничего в проде не менялось — старый плоский путь остаётся дефолтным до
явного решения включить флаг. Ветка `qaNew`, ничего не закоммичено.

## Зачем

`planner` в `agent/nodes.py` вызывал LLM с **всеми 35 инструментами** и **всем
853-строчным системным промптом** на каждый ход — даже для «мотивируй меня».
Это било по точности выбора инструмента, стоимости токенов и скорости ответа.

Решение: роутинг по 5 доменам (workout/nutrition/progress/motivation/general),
каждый со своим узким набором tools и своим куском промпта — паттерн
prompt → tools → sub-agents → memory, взятый из разбора `anthropics/agent-sdk-workshop`
(воркшоп по Claude Agent SDK) в этой же сессии.

## Что изменилось

### Новые файлы

| Файл | Назначение |
|---|---|
| `agent/router.py` | `TOOLS_BY_DOMAIN`, `DOMAIN_PROMPTS`, `classify_domain()` (LLM-классификатор), `resolve_domain()` |
| `agent/prompts/shared.py` | Общая шапка промпта (язык/tone/telegram_user_id) + формат ответов + `build_domain_prompt()` |
| `agent/prompts/{workout,nutrition,progress,motivation,general}.py` | Доменные куски промпта, извлечены дословно из старого `system.py` |
| `agent/tools/workouts/` (пакет) | `agent/tools/workouts.py` (2844 строк) разбит на `_shared.py`, `generation.py`, `session_log.py`, `recovery.py`, `cycles.py`, `sessions.py`, `analysis.py`, `debrief.py`, `__init__.py` (реэкспорт) |
| `tests/test_router.py` | 17 тестов: покрытие доменов, классификация, router_node, domain_planner, retry-хелпер, build_graph |
| `scripts/shadow_test_router.py` | Batch-сравнение flat vs routed graph на сценариях из `docs/use_cases.md` |

### Изменённые файлы

- `config.py` — добавлен `enable_subagent_router: bool = False`
- `.env.example` — задокументирован `ENABLE_SUBAGENT_ROUTER`
- `agent/state.py` — добавлено поле `active_domain: str`
- `agent/nodes.py` — добавлены `router_node`, `domain_planner`; retry-на-503 и
  коррекция галлюцинированного `telegram_user_id` вынесены в общие хелперы
  `_invoke_llm_with_retry` / `_correct_hallucinated_user_id` (переиспользуются
  старым `planner` и новым `domain_planner`, без дублирования)
- `agent/graph.py` — `build_graph()` разветвлён на `_build_flat_graph` (старый
  путь) и `_build_routed_graph` (новый), выбор по `settings.enable_subagent_router`
- `tests/tools/test_log_workout_upsert.py` — 27 патчей `agent.tools.workouts.X`
  переведены на `agent.tools.workouts.session_log.X` (функции физически
  переехали в этот модуль; без правки моки бы молча переставали работать)

## Архитектура нового пути

```
load_profile → router → domain_planner ⇄ tool_executor → responder
```

- `router` — если у пользователя явно выбран режим (кнопки 🏋️/🥗/📊/💪 из
  `chat_modes.py`) — маршрутизирует без LLM-вызова. Иначе — дешёвый
  LLM-классификатор (`get_llm()`, без thinking) на один из 5 доменов.
- `domain_planner` — параметризован `state["active_domain"]`: биндит только
  tools своего домена, использует только свой кусок промпта.
- `tool_executor` — **один** `ToolNode` над полным списком всех 35 tools (это
  исполнитель, а не источник схем для LLM — доменное ограничение работает
  только на этапе `bind_tools` внутри `domain_planner`).

## Shadow-test: результаты

Прогнан `scripts/shadow_test_router.py` на 6 сценариях из `docs/use_cases.md`
против настоящего Gemini (реальный `GEMINI_API_KEY` в `.env`), с замоканным
Supabase (реальная БД не трогалась).

- **6/6 доменов классифицированы верно.**
- Латентность ниже в 5 из 6 сценариев (например workout: 3.56s vs 7.35s).
- На motivation-сценарии routed-путь вызвал оба нужных инструмента
  (`send_motivation` + `generate_motivation_meme`), тогда как старый плоский
  planner вызвал только один — узкий набор tools улучшил точность следования
  промпту, не только скорость.
- **Найден и закрыт edge-case (UC-X02, «как прошёл день?»):** в домене
  `general` изначально не было доступа к сводкам питания/тренировок/прогресса,
  поэтому агент только переспрашивал вместо проактивного ответа. Добавлены
  `get_daily_nutrition_summary`, `get_workout_history`, `get_progress_summary`
  в `TOOLS_BY_DOMAIN["general"]` + новое правило в `agent/prompts/general.py`.
  После фикса — 3/3 нужных вызова.

## Известное ограничение

Домен фиксируется **один раз в начале хода** (`router` → `domain_planner`).
Если одно сообщение требует tools из двух НЕ-general доменов одновременно
(например «залогируй тренировку и покажи вес» в одной фразе) — новый путь
пока не решает это так же хорошо, как старый плоский planner (у которого были
все 35 tools сразу). В `docs/use_cases.md` явных примеров такого рода не
найдено — единственный обнаруженный кросс-доменный кейс (UC-X02) уже закрыт
через расширение general-домена. Если такие сценарии появятся в реальном
трафике — следующий шаг: loop-back из `tool_executor` в `router` вместо
прямого возврата в `domain_planner`, чтобы агент мог сменить домен в
середине хода.

## Как включить / откатить

```bash
# .env
ENABLE_SUBAGENT_ROUTER=true   # включить
ENABLE_SUBAGENT_ROUTER=false  # откат — мгновенный, без миграции данных
```

Откат безопасен в любой момент: старый `_build_flat_graph` не удалён и не
изменён по поведению, `MemorySaver`/`checkpoints.pkl` формат общий для обоих
путей (оба используют `AgentState.messages` с тем же reducer).

## Что дальше (требует решения человека)

1. Опционально: прогнать `scripts/shadow_test_router.py` против локального
   Ollama для сравнения dev-модели (сейчас проверено только на Gemini).
2. Включить `ENABLE_SUBAGENT_ROUTER=true` в проде — осознанное решение с
   реальным пользовательским трафиком, не автоматизировано намеренно.
