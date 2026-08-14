# База данных

## Стек (с 2026-08-14)

**PostgreSQL напрямую через `asyncpg`**, задеплоен как Railway Postgres addon. Supabase
(`supabase-py`, HTTP-обёртка над PostgREST) полностью выведен из проекта — решение
принято 2026-08-14 в рамках переноса бота на Railway.

Почему не оставили Supabase: `supabase-py` говорит с базой через PostgREST (HTTP), а не
напрямую по Postgres-протоколу. Чтобы уйти от Supabase-хостинга на Railway Postgres,
PostgREST-слоя больше нет — соответственно и клиент, завязанный на него, тоже пришлось
убрать. Миграция данных не делалась (осознанное решение пользователя) — Railway Postgres
стартовал с пустой схемой.

## `db/client.py` — слой доступа к данным

Три тонкие async-обёртки поверх `asyncpg.Pool`, вместо старого `get_client()` +
Supabase query-builder (`.table().select().eq()....execute()`):

```python
async def fetch(query: str, *args) -> list[dict]: ...     # SELECT, много строк
async def fetchrow(query: str, *args) -> dict | None: ...  # SELECT, 0 или 1 строка
async def execute(query: str, *args) -> str: ...           # INSERT/UPDATE/DELETE без RETURNING
```

Что делают эти обёртки автоматически (не дублировать в вызывающем коде):
- **jsonb** колонки возвращаются как нативный `dict`/`list` (codec зарегистрирован на pool
  при инициализации) — никогда не звать `json.loads`/`json.dumps` вручную.
- **uuid** и **timestamptz** колонки в возвращаемых `dict` уже сконвертированы в `str`
  (`str(uuid.UUID)` / `.isoformat()`) — остальной код (Pydantic-валидация, JSON-ответы
  LLM-тулов) как и раньше работает со строками, не с `uuid.UUID`/`datetime` объектами.

Важные грабли при написании новых запросов:
- Параметры — только `$1, $2, ...` (asyncpg-стиль), никогда не f-string со значениями
  в SQL (SQL injection).
- Если нужно прочитать вставленную/обновлённую строку — добавляй `RETURNING ...` и
  используй `fetchrow`/`fetch`, а не `execute`.
- **timestamptz-параметры должны быть нативным `datetime.datetime`, не ISO-строкой** —
  asyncpg (в отличие от Supabase/PostgREST по HTTP) кидает `DataError` на строку там,
  где ожидается `timestamptz`.
- `.single()`-семантику Supabase (кидает ошибку на 0 или >1 строк) заменяем на
  `fetchrow` + явную проверку `if row is None:`.

## Схема (`migrations/001_schema.sql`)

Таблицы: `users`, `workouts`, `training_cycles`, `workout_logs`, `nutrition_plans`,
`food_logs`, `progress_logs`. Без Row Level Security (не нужна без PostgREST-слоя с
JWT-ролями `anon`/`service_role` — Railway Postgres не имеет этих ролей вообще).
`gen_random_uuid()` вместо расширения `uuid-ossp`.

При переносе обнаружился и задокументирован schema drift: колонки
`workout_logs.performance` (jsonb) и `workout_logs.done_as_planned` (boolean)
использовались в коде повсеместно, но отсутствовали в старых Supabase-миграциях
(`migrations/001_initial_schema.sql` и др., теперь удалены) — были добавлены
напрямую через Supabase SQL Editor в обход версионирования. В новой схеме эти
колонки явно объявлены.

Бизнес-инвариант, перенесённый 1:1: частичный уникальный индекс
`idx_one_active_cycle ON training_cycles(user_id) WHERE status = 'active'`
(максимум один активный тренировочный цикл на пользователя).

## Применение схемы к новой БД

```bash
psql "$DATABASE_URL" -f migrations/001_schema.sql
```

На Railway (нет публичного TCP-прокси у Postgres addon по умолчанию — CLI `railway
connect`/`railway run` не достают до `postgres.railway.internal` снаружи): применяли
через `railway ssh -s bot`, т.к. этот сервис уже внутри той же приватной сети Railway
и имеет `asyncpg` в зависимостях. См. `docs/deployment.md`.

## Тестовые моки

`db.client.fetch`/`fetchrow`/`execute` мокаются напрямую (`AsyncMock` с `side_effect`
списком значений в порядке вызовов) — см. `tests/tools/test_log_workout_upsert.py`.
Это проще, чем старый Supabase chain-builder мок: не нужно эмулировать `.table()
.select().eq()...` цепочку, только порядок и возвращаемые значения `fetch`/`fetchrow`.
