-- Número opcional por jogador no elenco; 0 e 100 são válidos.
ALTER TABLE event_team_players ADD COLUMN IF NOT EXISTS jersey_number INTEGER;
ALTER TABLE club_members ADD COLUMN IF NOT EXISTS jersey_number INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_event_team_players_jersey_number_range') THEN
        ALTER TABLE event_team_players ADD CONSTRAINT ck_event_team_players_jersey_number_range
            CHECK (jersey_number BETWEEN 0 AND 100);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_club_members_jersey_number_range') THEN
        ALTER TABLE club_members ADD CONSTRAINT ck_club_members_jersey_number_range
            CHECK (jersey_number BETWEEN 0 AND 100);
    END IF;
END $$;
