-- Таблица профилей пользователей
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    full_name VARCHAR(255),
    age INT,
    gender VARCHAR(10),
    height FLOAT,
    activity_level VARCHAR(50),
    goal VARCHAR(50),
    medical_restrictions TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица истории веса (для графиков и аналитики)
CREATE TABLE IF NOT EXISTS weight_logs (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    weight FLOAT NOT NULL,
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
