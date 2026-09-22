-- Evolução aditiva para bancos criados antes do ciclo de vida dos eventos.
ALTER TABLE pelada_events
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS previous_match_id UUID,
    ADD COLUMN IF NOT EXISTS advancing_team_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_matches_previous_match') THEN
        ALTER TABLE matches ADD CONSTRAINT fk_matches_previous_match
            FOREIGN KEY (previous_match_id) REFERENCES matches(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_matches_advancing_team') THEN
        ALTER TABLE matches ADD CONSTRAINT fk_matches_advancing_team
            FOREIGN KEY (advancing_team_id) REFERENCES event_teams(id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_event_sequence
    ON matches(event_id, sequence);
CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_previous_match
    ON matches(previous_match_id)
    WHERE previous_match_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS event_team_queue_entries (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    event_id UUID NOT NULL REFERENCES pelada_events(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES event_teams(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    CONSTRAINT uq_event_team_queue_event_team UNIQUE (event_id, team_id),
    CONSTRAINT uq_event_team_queue_event_position UNIQUE (event_id, position),
    CONSTRAINT ck_event_team_queue_positive_position CHECK (position > 0)
);
