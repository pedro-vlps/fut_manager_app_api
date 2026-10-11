BEGIN;
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS home_goalkeeper_id UUID REFERENCES profiles(id);
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS away_goalkeeper_id UUID REFERENCES profiles(id);
COMMIT;
