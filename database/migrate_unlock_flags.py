"""One-time migration: add nutrition_unlocked and workout_unlocked columns."""
import asyncio
from database.engine import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS nutrition_unlocked BOOLEAN NOT NULL DEFAULT FALSE"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS workout_unlocked BOOLEAN NOT NULL DEFAULT FALSE"
        )
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
