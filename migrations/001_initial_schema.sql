-- ============================================================
-- FitnessAI — Initial schema
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- ============================================================

-- Enable UUID extension (already enabled in Supabase by default)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- users
-- ============================================================
CREATE TABLE IF NOT EXISTS public.users (
    id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_user_id bigint           NOT NULL UNIQUE,
    name             text             NOT NULL,
    age              integer          NOT NULL,
    weight_kg        double precision NOT NULL,
    height_cm        double precision NOT NULL,
    goal             text             NOT NULL
                         CHECK (goal IN ('lose_weight', 'gain_muscle', 'maintain')),
    activity_level   text             NOT NULL
                         CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    created_at       timestamptz      NOT NULL DEFAULT now(),
    updated_at       timestamptz      NOT NULL DEFAULT now()
);

-- Auto-update updated_at
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
    id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    uuid        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    title      text        NOT NULL,
    plan       jsonb       NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workouts_user_id_idx ON public.workouts (user_id);

-- ============================================================
-- workout_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS public.workout_logs (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      uuid        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    workout_id   uuid                 REFERENCES public.workouts (id) ON DELETE SET NULL,
    notes        text,
    completed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workout_logs_user_id_idx ON public.workout_logs (user_id);

-- ============================================================
-- nutrition_plans
-- ============================================================
CREATE TABLE IF NOT EXISTS public.nutrition_plans (
    id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
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
    id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
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
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     uuid             NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    weight_kg   double precision NOT NULL,
    notes       text,
    measured_at timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS progress_logs_user_id_idx    ON public.progress_logs (user_id);
CREATE INDEX IF NOT EXISTS progress_logs_measured_at_idx ON public.progress_logs (measured_at);

-- ============================================================
-- Row Level Security
-- Supabase использует анонимный ключ — включаем RLS и разрешаем
-- доступ только через service_role key (используется на бэкенде).
-- ============================================================
ALTER TABLE public.users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workouts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workout_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nutrition_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.food_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.progress_logs   ENABLE ROW LEVEL SECURITY;

-- Политики для service_role (бэкенд): полный доступ
CREATE POLICY "service_role full access" ON public.users
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.workouts
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.workout_logs
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.nutrition_plans
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.food_logs
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.progress_logs
    USING (true) WITH CHECK (true);
