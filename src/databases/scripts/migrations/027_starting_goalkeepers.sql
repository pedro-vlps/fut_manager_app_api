BEGIN;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS starting_goalkeeper_id UUID REFERENCES profiles(id);
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS starting_goalkeeper_id UUID REFERENCES profiles(id);
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS home_goalkeeper_override BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS away_goalkeeper_override BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS goalkeeper_history JSONB NOT NULL DEFAULT '[]';
-- Preserva escolhas manuais legadas sem marcar os novos padrões como overrides.
UPDATE championship_matches SET home_goalkeeper_override = true
 WHERE home_goalkeeper_id IS NOT NULL AND started_at IS NULL AND goalkeeper_history = '[]'::jsonb
 AND NOT EXISTS (SELECT 1 FROM championship_entries e WHERE e.championship_id = championship_matches.championship_id
     AND e.club_id = championship_matches.home_id AND e.starting_goalkeeper_id IS NOT NULL);
UPDATE championship_matches SET away_goalkeeper_override = true
 WHERE away_goalkeeper_id IS NOT NULL AND started_at IS NULL AND goalkeeper_history = '[]'::jsonb
 AND NOT EXISTS (SELECT 1 FROM championship_entries e WHERE e.championship_id = championship_matches.championship_id
     AND e.club_id = championship_matches.away_id AND e.starting_goalkeeper_id IS NOT NULL);
-- Súmulas já iniciadas continuam protegidas contra mudanças feitas pelos times.
UPDATE championship_matches SET started_at = created_at WHERE started_at IS NULL
 AND home_score IS NULL AND actions IS NOT NULL AND actions <> '[]' AND actions NOT LIKE 'enc:v1:%';
COMMIT;
