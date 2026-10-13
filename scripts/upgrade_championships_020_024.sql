-- Atualização de banco existente para campeonatos: migrations 020 a 024.
-- Pode ser reaplicada; preserva dados. Se a sessão estiver em erro, execute ROLLBACK antes.
BEGIN;

-- 020_championship_actions.sql
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS actions JSONB NOT NULL DEFAULT '[]'::jsonb;

-- 021_league_championships.sql
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_championship_format;
ALTER TABLE championships ADD CONSTRAINT ck_championships_championship_format
    CHECK (format IN ('groups_knockout', 'knockout', 'cascade', 'league'));

-- 022_league_home_and_away.sql
ALTER TABLE championships ADD COLUMN IF NOT EXISTS home_and_away BOOLEAN NOT NULL DEFAULT false;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_championships_league_home_and_away'
                   AND conrelid = 'championships'::regclass) THEN
        ALTER TABLE championships ADD CONSTRAINT ck_championships_league_home_and_away
            CHECK (NOT home_and_away OR format = 'league');
    END IF;
END $$;

-- 023_championship_goalkeepers.sql
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS home_goalkeeper_id UUID REFERENCES profiles(id);
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS away_goalkeeper_id UUID REFERENCES profiles(id);

-- 024_championship_groups.sql
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_championship_capacity;
ALTER TABLE championships ADD CONSTRAINT ck_championships_championship_capacity
    CHECK (capacity IN (4, 8, 12, 16));
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_twelve_teams_groups;
ALTER TABLE championships ADD CONSTRAINT ck_championships_twelve_teams_groups
    CHECK (capacity <> 12 OR format = 'groups_knockout');
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS pool VARCHAR(1);

COMMIT;
