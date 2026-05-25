-- Add injuries/contraindications column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS injuries jsonb DEFAULT '[]'::jsonb;
COMMENT ON COLUMN users.injuries IS 'Список травм/противопоказаний, напр. ["knee_injury", "lower_back"]';
