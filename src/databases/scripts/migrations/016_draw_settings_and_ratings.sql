CREATE TABLE IF NOT EXISTS group_draw_settings (
    group_id uuid PRIMARY KEY REFERENCES pelada_groups(id) ON DELETE CASCADE,
    use_positions boolean NOT NULL DEFAULT false,
    use_ratings boolean NOT NULL DEFAULT false,
    use_wins boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS group_player_ratings (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    group_id uuid NOT NULL REFERENCES pelada_groups(id) ON DELETE CASCADE,
    profile_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    rating numeric(3, 1) NOT NULL CHECK (rating >= 0 AND rating <= 10),
    updated_by_id uuid REFERENCES profiles(id) ON DELETE SET NULL,
    UNIQUE (group_id, profile_id)
);
