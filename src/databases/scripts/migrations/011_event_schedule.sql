ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS recurring_weekly boolean NOT NULL DEFAULT false;
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS schedule_timezone varchar(80) NOT NULL DEFAULT 'America/Sao_Paulo';
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS recurrence_parent_id uuid REFERENCES pelada_events(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_recurrence_parent ON pelada_events(recurrence_parent_id);
