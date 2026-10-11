BEGIN;
ALTER TABLE championships ADD COLUMN IF NOT EXISTS home_and_away BOOLEAN NOT NULL DEFAULT false;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_championships_league_home_and_away'
                   AND conrelid = 'championships'::regclass) THEN
        ALTER TABLE championships ADD CONSTRAINT ck_championships_league_home_and_away
            CHECK (NOT home_and_away OR format = 'league');
    END IF;
END $$;
COMMIT;
