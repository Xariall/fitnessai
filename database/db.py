"""SQLite database: connection, schema init, CRUD helpers."""

import aiosqlite
import os
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent / "fitness.db"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    age         INTEGER,
    height      REAL,
    weight      REAL,
    gender      TEXT CHECK(gender IN ('male', 'female')),
    activity    TEXT CHECK(activity IN ('sedentary', 'moderate', 'active', 'athlete')),
    goal        TEXT CHECK(goal IN ('lose', 'maintain', 'gain', 'recomposition')),
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weight_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weight      REAL NOT NULL,
    logged_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    muscle_group TEXT NOT NULL,
    equipment   TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS workout_programs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    goal            TEXT,
    level           TEXT,
    days_per_week   INTEGER,
    program_json    TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workout_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise    TEXT NOT NULL,
    sets        INTEGER NOT NULL,
    reps        INTEGER NOT NULL,
    weight_kg   REAL,
    logged_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS food_products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    calories    REAL NOT NULL,
    protein     REAL NOT NULL,
    fat         REAL NOT NULL,
    carbs       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS food_diary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    weight_g    REAL NOT NULL,
    calories    REAL NOT NULL,
    protein     REAL NOT NULL,
    fat         REAL NOT NULL,
    carbs       REAL NOT NULL,
    logged_at   TEXT DEFAULT (datetime('now'))
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    finally:
        await db.close()


# ── Users ───────────────────────────────────────────────────────────────

async def ensure_user(user_id: str):
    """Create a minimal user record if it doesn't exist yet."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        )
        if not rows:
            await db.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
            await db.commit()
    finally:
        await db.close()


async def upsert_user(user_id: str, **fields) -> dict:
    db = await get_db()
    try:
        existing = await db.execute_fetchall(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [user_id]
            await db.execute(
                f"UPDATE users SET {sets}, updated_at = datetime('now') WHERE id = ?",
                vals,
            )
        else:
            fields["id"] = user_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" for _ in fields)
            await db.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})",
                list(fields.values()),
            )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        return dict(row[0]) if row else {}
    finally:
        await db.close()


async def get_user(user_id: str) -> dict | None:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        return dict(rows[0]) if rows else None
    finally:
        await db.close()


# ── Weight ──────────────────────────────────────────────────────────────

async def log_weight(user_id: str, weight: float):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO weight_logs (user_id, weight) VALUES (?, ?)",
            (user_id, weight),
        )
        await db.execute(
            "UPDATE users SET weight = ?, updated_at = datetime('now') WHERE id = ?",
            (weight, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_weight_history(user_id: str, days: int = 30) -> list[dict]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT weight, logged_at FROM weight_logs
               WHERE user_id = ? AND logged_at >= datetime('now', ?)
               ORDER BY logged_at DESC""",
            (user_id, f"-{days} days"),
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Exercises ───────────────────────────────────────────────────────────

async def get_exercises(muscle_group: str | None = None) -> list[dict]:
    db = await get_db()
    try:
        if muscle_group:
            rows = await db.execute_fetchall(
                "SELECT * FROM exercises WHERE muscle_group = ?",
                (muscle_group,),
            )
        else:
            rows = await db.execute_fetchall("SELECT * FROM exercises")
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Workout programs ───────────────────────────────────────────────────

async def save_workout_program(user_id: str, name: str, goal: str,
                                level: str, days: int, program_json: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO workout_programs
               (user_id, name, goal, level, days_per_week, program_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, name, goal, level, days, program_json),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_workout_programs(user_id: str) -> list[dict]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM workout_programs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Workout logs ────────────────────────────────────────────────────────

async def log_workout(user_id: str, exercise: str, sets: int,
                       reps: int, weight_kg: float | None = None):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workout_logs (user_id, exercise, sets, reps, weight_kg)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, exercise, sets, reps, weight_kg),
        )
        await db.commit()
    finally:
        await db.close()


async def get_workout_logs(user_id: str, date: str | None = None) -> list[dict]:
    db = await get_db()
    try:
        if date:
            rows = await db.execute_fetchall(
                """SELECT * FROM workout_logs
                   WHERE user_id = ? AND date(logged_at) = ?
                   ORDER BY logged_at DESC""",
                (user_id, date),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM workout_logs
                   WHERE user_id = ? ORDER BY logged_at DESC LIMIT 50""",
                (user_id,),
            )
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Food products ───────────────────────────────────────────────────────

async def search_food(query: str) -> list[dict]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM food_products WHERE name LIKE ?",
            (f"%{query}%",),
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Food diary ──────────────────────────────────────────────────────────

async def log_meal(user_id: str, product_name: str, weight_g: float,
                    calories: float, protein: float, fat: float, carbs: float):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO food_diary
               (user_id, product_name, weight_g, calories, protein, fat, carbs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, product_name, weight_g, calories, protein, fat, carbs),
        )
        await db.commit()
    finally:
        await db.close()


async def get_food_diary(user_id: str, date: str | None = None) -> list[dict]:
    db = await get_db()
    try:
        target = date or "date('now')"
        if date:
            rows = await db.execute_fetchall(
                """SELECT * FROM food_diary
                   WHERE user_id = ? AND date(logged_at) = ?
                   ORDER BY logged_at""",
                (user_id, date),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM food_diary
                   WHERE user_id = ? AND date(logged_at) = date('now')
                   ORDER BY logged_at""",
                (user_id,),
            )
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_daily_summary(user_id: str, date: str | None = None) -> dict:
    entries = await get_food_diary(user_id, date)
    totals = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "meals": len(entries)}
    for e in entries:
        totals["calories"] += e["calories"]
        totals["protein"] += e["protein"]
        totals["fat"] += e["fat"]
        totals["carbs"] += e["carbs"]
    for k in ("calories", "protein", "fat", "carbs"):
        totals[k] = round(totals[k], 1)
    return totals
