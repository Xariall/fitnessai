"""Async SQLAlchemy engine and session factory."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base  # noqa: F401 – imported so Alembic sees all models

def _async_db_url(raw: str) -> str:
    """Normalize DATABASE_URL to use the asyncpg driver.

    Railway (and Heroku) provide plain postgresql:// or postgres:// URLs.
    asyncpg requires the postgresql+asyncpg:// scheme.
    """
    raw = raw.replace("postgres://", "postgresql://", 1)
    if not raw.startswith("postgresql+asyncpg://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


_raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fitagent",
)
DATABASE_URL = _async_db_url(_raw_url)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables. Used in development; production uses Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
