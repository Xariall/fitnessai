-- Migration 003: Training cycles (persistent program progression)
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS public.training_cycles (
    id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
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

ALTER TABLE public.training_cycles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role full access" ON public.training_cycles
    USING (true) WITH CHECK (true);

-- Extend workout_logs with cycle tracking columns
ALTER TABLE public.workout_logs
    ADD COLUMN IF NOT EXISTS cycle_id uuid REFERENCES public.training_cycles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cycle_week integer,
    ADD COLUMN IF NOT EXISTS cycle_session_index integer;

CREATE INDEX IF NOT EXISTS idx_workout_logs_cycle_id
    ON public.workout_logs (cycle_id);

CREATE INDEX IF NOT EXISTS idx_workout_logs_user_cycle
    ON public.workout_logs (user_id, cycle_id);

-- Add new columns to existing table (idempotent if running on already-created table)
ALTER TABLE public.training_cycles
    ADD COLUMN IF NOT EXISTS training_type text,
    ADD COLUMN IF NOT EXISTS equipment     text,
    ADD COLUMN IF NOT EXISTS paused_at     timestamptz;
