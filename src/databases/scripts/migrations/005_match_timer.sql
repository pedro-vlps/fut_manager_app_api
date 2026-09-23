-- Preserva as partidas existentes e inicia seus cronômetros pausados.
ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS timer_elapsed_ms INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS timer_running_since TIMESTAMP WITH TIME ZONE;
