-- Preserve past lineups and actions. New substitutions mark the outgoing player inactive.
ALTER TABLE match_lineups ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE match_lineups ADD COLUMN IF NOT EXISTS replaced_lineup_id uuid REFERENCES match_lineups(id);
