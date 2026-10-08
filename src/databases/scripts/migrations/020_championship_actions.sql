ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS actions JSONB NOT NULL DEFAULT '[]'::jsonb;
