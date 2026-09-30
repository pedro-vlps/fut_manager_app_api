ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_mode varchar(10) NOT NULL DEFAULT 'days';
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_months integer NOT NULL DEFAULT 3;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_day integer NOT NULL DEFAULT 10;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_fixed_end timestamptz;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_timezone varchar(80) NOT NULL DEFAULT 'America/Sao_Paulo';
