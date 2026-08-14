# Daily changes

Лог изменений по дням. Раньше вёлся в Obsidian-vault (см. корневой `CLAUDE.md`);
с 2026-08-14 Obsidian-MCP в этом окружении недоступен (`fetch failed` — не поднят
Local REST API плагин), поэтому лог и остальная документация ведутся в этой папке
(`docs/`) + в графе `mcp__memory` — по решению пользователя.

---

## 2026-08-14

**Миграция Supabase → PostgreSQL (Railway) + деплой.**

- Полностью убрали `supabase-py` (PostgREST-клиент), заменили на `asyncpg` напрямую.
  ~110 вызовов в 20 файлах переведены на `db/client.py`'s `fetch`/`fetchrow`/`execute`.
  Подробности архитектуры — `docs/database.md`.
- Новая схема `migrations/001_schema.sql` (старые 3 Supabase-миграции удалены,
  история не сохранялась — DDL описывает конечное состояние). Без RLS, `gen_random_uuid()`.
- Задеплоено на Railway: новый проект `fitnessai`, сервисы `bot` + `api`
  (`Dockerfile.api`), Postgres addon. Подробности — `docs/deployment.md`.
- По пути пойманы и исправлены два реальных бага, всплывших только на живом деплое:
  1. `bot/handlers/start.py` — блокирующий `INSERT` без `ON CONFLICT` падал
     `UniqueViolationError`, если уже зарегистрированный пользователь повторно проходил
     онбординг (кнопка «давай начнём» не была защищена проверкой регистрации,
     т.к. `UserMiddleware` вешался только на `Message`-события, не на `CallbackQuery`).
     Исправлено на `INSERT ... ON CONFLICT (telegram_user_id) DO UPDATE`.
  2. Более серьёзный: кнопка «Нет травм ✅» (callback_query) передавала в
     `_finish_onboarding` объект `callback.message` (сообщение, отправленное ботом) —
     внутри бралось `message.from_user.id`, которое для сообщения бота равно ID
     самого бота, а не нажавшего пользователя. Профиль сохранялся под чужим
     (ботовским) telegram_user_id. Пользователь после онбординга не проходил проверку
     регистрации под своим настоящим ID и попадал в бесконечный цикл `/start`.
     Исправлено: `_finish_onboarding` теперь принимает `user_id` явным параметром
     (`callback.from_user.id` из кнопки, `message.from_user.id` из текстового ввода).
     Проверено, что больше нигде в `bot/` нет той же путаницы `callback.message.from_user`
     vs `callback.from_user`.
- Заодно закоммичен (но не запушен) sub-agent router из прошлой сессии
  (`ENABLE_SUBAGENT_ROUTER`, по умолчанию `false`) — он существовал только в
  рабочей директории, теперь в git-истории. Не включён в проде, статус не менялся.
- Коммит `66b5141` на ветке `qaNew`, ветка на 1 коммит впереди `origin/qaNew`
  (не запушено на момент записи).
- Известный хвост: дублирующийся Postgres-сервис `Postgres-JQ6u` в Railway (CLI
  случайно создал его дважды, CLI не умеет удалять сервисы) — почистить вручную
  в дашборде. См. `docs/deployment.md`.
