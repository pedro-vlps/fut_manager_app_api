CREATE TABLE IF NOT EXISTS season_trophies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id UUID NOT NULL REFERENCES group_seasons(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES profiles(id),
    category VARCHAR(32) NOT NULL,
    title VARCHAR(250) NOT NULL,
    value INTEGER NOT NULL,
    awarded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, profile_id, category)
);
CREATE INDEX IF NOT EXISTS ix_season_trophies_profile_id ON season_trophies(profile_id);
