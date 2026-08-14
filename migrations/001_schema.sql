-- ============================================================
-- FitnessAI — schema (plain PostgreSQL, Railway)
-- Run once against a fresh database: psql "$DATABASE_URL" -f migrations/001_schema.sql
-- ============================================================

-- gen_random_uuid() is built into Postgres 13+; pgcrypto guards older versions.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- users
-- ============================================================
CREATE TABLE IF NOT EXISTS public.users (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id bigint           NOT NULL UNIQUE,
    name             text             NOT NULL,
    age              integer          NOT NULL,
    weight_kg        double precision NOT NULL,
    height_cm        double precision NOT NULL,
    goal             text             NOT NULL
                         CHECK (goal IN ('lose_weight', 'gain_muscle', 'maintain')),
    activity_level   text             NOT NULL
                         CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    injuries         jsonb            NOT NULL DEFAULT '[]'::jsonb,
    created_at       timestamptz      NOT NULL DEFAULT now(),
    updated_at       timestamptz      NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- workouts
-- ============================================================
CREATE TABLE IF NOT EXISTS public.workouts (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    title      text        NOT NULL,
    plan       jsonb       NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workouts_user_id_idx ON public.workouts (user_id);

-- ============================================================
-- training_cycles
-- ============================================================
CREATE TABLE IF NOT EXISTS public.training_cycles (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title                 text        NOT NULL,
    goal                  text        NOT NULL,
    total_weeks           integer     NOT NULL,
    sessions_per_week     integer     NOT NULL DEFAULT 3,
    training_type         text,                            -- strength | hypertrophy | functional | mixed
    equipment             text,                            -- gym | home_dumbbells | bodyweight
    schedule              jsonb       NOT NULL DEFAULT '{}',
    -- schedule JSON structure:
    -- {"weeks": [{"week_number": 1, "theme": "Накопление", "phase": "accumulation",
    --   "sessions": [{"session_index": 0, "focus": "chest", "label": "Грудь / Трицепс"}]}]}
    schedule_history      jsonb,
    current_week          integer     NOT NULL DEFAULT 1,
    current_session_index integer     NOT NULL DEFAULT 0,  -- 0-based within week
    total_sessions_done   integer     NOT NULL DEFAULT 0,
    status                text        NOT NULL DEFAULT 'active',  -- active/completed/paused
    started_at            timestamptz NOT NULL DEFAULT now(),
    completed_at          timestamptz,
    paused_at             timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_training_cycles_user_status
    ON public.training_cycles (user_id, status);

-- Prevent two active cycles per user at DB level
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_cycle
    ON public.training_cycles (user_id)
    WHERE status = 'active';

-- ============================================================
-- workout_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS public.workout_logs (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              uuid        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    workout_id           uuid                 REFERENCES public.workouts (id) ON DELETE SET NULL,
    cycle_id             uuid                 REFERENCES public.training_cycles(id) ON DELETE SET NULL,
    cycle_week           integer,
    cycle_session_index  integer,
    notes                text,
    performance          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    done_as_planned      boolean     NOT NULL DEFAULT false,
    completed_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workout_logs_user_id_idx    ON public.workout_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_workout_logs_cycle_id   ON public.workout_logs (cycle_id);
CREATE INDEX IF NOT EXISTS idx_workout_logs_user_cycle ON public.workout_logs (user_id, cycle_id);

-- ============================================================
-- nutrition_plans
-- ============================================================
CREATE TABLE IF NOT EXISTS public.nutrition_plans (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid             NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    target_calories  integer          NOT NULL,
    target_protein   double precision NOT NULL,
    target_fat       double precision NOT NULL,
    target_carbs     double precision NOT NULL,
    plan             jsonb            NOT NULL DEFAULT '{}',
    created_at       timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS nutrition_plans_user_id_idx ON public.nutrition_plans (user_id);

-- ============================================================
-- food_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS public.food_logs (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   uuid             NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    food_name text             NOT NULL,
    calories  integer          NOT NULL,
    protein   double precision NOT NULL,
    fat       double precision NOT NULL,
    carbs     double precision NOT NULL,
    meal_type text             NOT NULL
                  CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    logged_at timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS food_logs_user_id_idx  ON public.food_logs (user_id);
CREATE INDEX IF NOT EXISTS food_logs_logged_at_idx ON public.food_logs (logged_at);

-- ============================================================
-- progress_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS public.progress_logs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid             NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    weight_kg   double precision NOT NULL,
    notes       text,
    measured_at timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS progress_logs_user_id_idx     ON public.progress_logs (user_id);
CREATE INDEX IF NOT EXISTS progress_logs_measured_at_idx ON public.progress_logs (measured_at);
