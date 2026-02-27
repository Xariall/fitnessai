"""Асинхронный модуль для работы с PostgreSQL через asyncpg."""

import asyncpg
import os
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Создаёт пул соединений с PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASS", "admin"),
                database=os.getenv("DB_NAME", "fitness_ai"),
                host=os.getenv("DB_HOST", "db"),
            )
            logger.info("✅ Успешное подключение к PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def init_tables(self):
        """Создаёт таблицы из init.sql, если их ещё нет."""
        init_sql_path = os.path.join(
            os.path.dirname(__file__), "init.sql"
        )
        with open(init_sql_path, "r") as f:
            sql = f.read()

        async with self.pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("✅ Таблицы БД инициализированы")

    async def upsert_user(self, user_data: dict):
        """Создаёт или обновляет профиль пользователя."""
        query = """
            INSERT INTO users (
                telegram_id, username, full_name, age, gender,
                height, activity_level, goal, medical_restrictions
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender,
                height = EXCLUDED.height,
                activity_level = EXCLUDED.activity_level,
                goal = EXCLUDED.goal,
                medical_restrictions = EXCLUDED.medical_restrictions,
                updated_at = CURRENT_TIMESTAMP;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                user_data["telegram_id"],
                user_data.get("username"),
                user_data.get("full_name"),
                user_data.get("age"),
                user_data.get("gender"),
                user_data.get("height"),
                user_data.get("activity_level"),
                user_data.get("goal"),
                user_data.get("medical_restrictions"),
            )

    async def get_user(self, telegram_id: int) -> dict | None:
        """Возвращает профиль пользователя или None."""
        query = "SELECT * FROM users WHERE telegram_id = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, telegram_id)
            return dict(row) if row else None

    async def log_weight(self, telegram_id: int, weight: float):
        """Добавляет запись о текущем весе пользователя."""
        query = "INSERT INTO weight_logs (telegram_id, weight) VALUES ($1, $2);"
        async with self.pool.acquire() as conn:
            await conn.execute(query, telegram_id, weight)

    async def get_weight_history(self, telegram_id: int) -> list[dict]:
        """Возвращает историю веса пользователя."""
        query = """
            SELECT weight, logged_at
            FROM weight_logs
            WHERE telegram_id = $1
            ORDER BY logged_at DESC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, telegram_id)
            return [dict(r) for r in rows]

    async def close(self):
        """Закрывает пул соединений."""
        if self.pool:
            await self.pool.close()
            logger.info("🔒 Пул соединений с БД закрыт")
