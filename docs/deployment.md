# Деплой (Railway)

## Проект

Railway-проект **`fitnessai`** (workspace "Asanali Esmagambetov's Projects"), создан
2026-08-14. Отдельный от двух уже существовавших в аккаунте проектов
(`radiant-playfulness` — сервис `ivc_ragbot`, не относится к этому боту;
`sincere-patience` — не проверялся, тоже не этот бот).

Project ID: `3420e17e-9817-48a8-abd9-e72a9436b8c6`.

## Сервисы

| Сервис | Назначение | Build | Публичный URL |
|---|---|---|---|
| `bot` | Telegram-бот (aiogram polling) | `Dockerfile` (`CMD python -m bot.main`) | нет (не нужен, long-polling) |
| `api` | FastAPI backend для web-миниаппы рекордов | `Dockerfile.api` (`CMD uvicorn api.app:app`) | `https://api-production-b254.up.railway.app` |
| `Postgres` | БД | образ `ghcr.io/railwayapp-templates/postgres-ssl` | нет публичного TCP-прокси (см. ниже) |

`api`-сервис собирается из отдельного `Dockerfile.api` (не общего `Dockerfile`) —
переключение через переменную окружения сервиса `RAILWAY_DOCKERFILE_PATH=Dockerfile.api`.
Оба Dockerfile идентичны кроме последней строки `CMD`.

## Переменные окружения

`DATABASE_URL` на обоих (`bot`, `api`) — reference-переменная `${{Postgres.DATABASE_URL}}`,
подтягивается автоматически из Postgres addon, руками не прописывается.

На `bot`: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`,
`IMGFLIP_USERNAME`, `IMGFLIP_PASSWORD`, `ENABLE_SUBAGENT_ROUTER=false`.

На `api`: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL` — да, `api` реально их
не использует, но `config.py`'s `Settings()` требует `telegram_bot_token` как
обязательное поле (без default) и падает при импорте, если переменной нет — `db/client.py`
транзитивно тянет `config.settings`. Не убирать эти переменные с `api`, пока
`telegram_bot_token` в `config.py` обязательный.

## Известные особенности инфраструктуры

- **Нет публичного TCP-прокси у Postgres addon по умолчанию.** `railway connect`/
  `railway run psql` изнутри локальной машины не работают («Connection URL should
  point to the Railway TCP proxy»). Включается вручную в дашборде (Settings →
  Networking → TCP Proxy), через CLI 4.36.1 такого флоу не нашлось. Схему накатывали
  в обход — через `railway ssh -s bot -- python3 ...` (bot-сервис уже внутри приватной
  сети проекта и резолвит `postgres.railway.internal`).
- **CLI не умеет удалять сервисы.** По ошибке при провижининге дважды выполнилась
  `railway add -d postgres`, получилось два Postgres-сервиса: `Postgres` (используется)
  и **`Postgres-JQ6u` (мусорный дубликат, не подключён нигде, не удалён — почисти
  вручную в дашборде Railway, если хочешь не платить за лишний volume)**.
- По той же причине на `Postgres`-сервисе висит лишний HTTP-домен
  (`postgres-production-44bca.up.railway.app`) — создан по ошибке при попытке
  получить публичный доступ к БД, Postgres по HTTP не отвечает осмысленно, безвреден,
  можно удалить вручную.

## Как задеплоить изменения

```bash
railway up -s bot --ci --detach   # бот
railway up -s api --ci --detach   # api
```

Билд идёт из текущего состояния рабочей директории (`railway up` тарит и грузит
локальную папку как есть, **не требует git commit** перед деплоем — но коммитить
всё равно стоит для истории).

Проверка статуса:
```bash
railway status --json
railway logs -s bot --latest --lines 50
railway logs -s api --latest --lines 50
```

## Известные развязки зависимостей

`requirements.txt`: `fastapi==0.115.6` (не более новый) — `aiogram==3.10.0` требует
`pydantic<2.9`, а актуальные версии `fastapi` (0.13x+) требуют `pydantic>=2.9`. Эта пара
версий подобрана явно совместимой; при апгрейде `aiogram` или `fastapi` в будущем —
перепроверить чистой установкой (`pip install -r requirements.txt` в свежем venv/образе),
локальный dev-venv мог накопить более новые версии транзитивных пакетов и замаскировать
конфликт (так и произошло один раз при первом деплое `api`-сервиса).

## Данные

Начали с чистой схемы 2026-08-14, данные из Supabase не переносились (осознанное
решение — старых пользователей на проде не было). Тестовый профиль, случайно
сохранённый под `telegram_user_id` самого бота (баг, см. `daily-changes.md`), удалён
вручную.
