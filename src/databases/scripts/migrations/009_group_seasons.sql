ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS seasons_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_duration_days INTEGER NOT NULL DEFAULT 30;
CREATE TABLE IF NOT EXISTS group_seasons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES pelada_groups(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    archived_rankings JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (group_id, number),
    CONSTRAINT season_positive_period CHECK (ends_at > starts_at)
);
