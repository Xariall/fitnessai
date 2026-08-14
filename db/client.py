import datetime
import json
import logging
import uuid

import asyncpg

from config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    """Возвращает singleton connection pool для Postgres (Railway)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, init=_init_connection)
        logger.info("Postgres pool initialized")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _coerce(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def _row(record: asyncpg.Record | None) -> dict | None:
    if record is None:
        return None
    return {key: _coerce(value) for key, value in dict(record).items()}


async def fetch(query: str, *args) -> list[dict]:
    """SELECT возвращающий несколько строк, как list[dict]."""
    pool = await get_pool()
    rows = await pool.fetch(query, *args)
    return [_row(r) for r in rows]


async def fetchrow(query: str, *args) -> dict | None:
    """SELECT возвращающий не более одной строки, как dict или None."""
    pool = await get_pool()
    return _row(await pool.fetchrow(query, *args))


async def execute(query: str, *args) -> str:
    """INSERT/UPDATE/DELETE без RETURNING. Возвращает command tag (напр. 'UPDATE 1')."""
    pool = await get_pool()
    return await pool.execute(query, *args)
