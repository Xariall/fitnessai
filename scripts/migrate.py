"""
Smart Alembic migration runner.

Three scenarios handled automatically:
  1. Fresh DB (no tables)        → alembic upgrade head  (creates schema)
  2. Pre-Alembic DB (has tables, no alembic_version)
                                 → alembic stamp head    (mark current state as v001)
  3. Alembic-tracked DB          → alembic upgrade head  (apply pending migrations)
"""
import asyncio
import os
import subprocess
import sys

import asyncpg

from database.engine import _async_db_url


def _get_db_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set. Add a Postgres plugin in Railway.", file=sys.stderr)
        sys.exit(1)
    return raw


async def inspect_db() -> tuple[bool, bool]:
    raw = _get_db_url()
    # asyncpg.connect needs plain postgresql:// (no driver prefix)
    url = _async_db_url(raw).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        has_alembic = bool(
            await conn.fetchval("SELECT to_regclass('public.alembic_version')")
        )
        has_tables = bool(
            await conn.fetchval("SELECT to_regclass('public.users')")
        )
        return has_alembic, has_tables
    finally:
        await conn.close()


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    has_alembic, has_tables = asyncio.run(inspect_db())

    if has_alembic:
        print("▶ Alembic version found — running upgrade head...")
        run(["alembic", "upgrade", "head"])
    elif has_tables:
        print("▶ Tables exist without Alembic tracking — stamping as head...")
        run(["alembic", "stamp", "head"])
        print("✓ Existing database registered with Alembic (revision 001).")
    else:
        print("▶ Fresh database — running migrations from scratch...")
        run(["alembic", "upgrade", "head"])

    print("✓ Database schema is up to date.")


if __name__ == "__main__":
    main()
