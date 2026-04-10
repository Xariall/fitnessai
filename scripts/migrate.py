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


async def inspect_db() -> tuple[bool, bool]:
    raw = os.environ["DATABASE_URL"]
    # Normalize to plain postgresql:// for asyncpg.connect (strips driver prefix)
    url = raw.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
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
