-- Capacidade de confirmações, lista de espera e validação de início do evento.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pelada_events' AND column_name = 'max_players'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pelada_events' AND column_name = 'max_confirmed_players'
    ) THEN
        ALTER TABLE pelada_events RENAME COLUMN max_players TO max_confirmed_players;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pelada_events' AND column_name = 'min_confirmed_players'
    ) THEN
        ALTER TABLE pelada_events ADD COLUMN min_confirmed_players INTEGER;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'event_presences' AND column_name = 'queue_position'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'event_presences' AND column_name = 'waitlist_position'
    ) THEN
        ALTER TABLE event_presences RENAME COLUMN queue_position TO waitlist_position;
    END IF;
END $$;

ALTER TABLE pelada_events
    DROP CONSTRAINT IF EXISTS ck_pelada_events_positive_max_players;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_pelada_events_positive_min_confirmed_players') THEN
        ALTER TABLE pelada_events ADD CONSTRAINT ck_pelada_events_positive_min_confirmed_players
            CHECK (min_confirmed_players IS NULL OR min_confirmed_players > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_pelada_events_positive_max_confirmed_players') THEN
        ALTER TABLE pelada_events ADD CONSTRAINT ck_pelada_events_positive_max_confirmed_players
            CHECK (max_confirmed_players IS NULL OR max_confirmed_players > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_pelada_events_min_confirmed_not_greater_than_max') THEN
        ALTER TABLE pelada_events ADD CONSTRAINT ck_pelada_events_min_confirmed_not_greater_than_max
            CHECK (min_confirmed_players IS NULL OR max_confirmed_players IS NULL OR min_confirmed_players <= max_confirmed_players);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_event_presences_positive_waitlist_position') THEN
        ALTER TABLE event_presences ADD CONSTRAINT ck_event_presences_positive_waitlist_position
            CHECK (waitlist_position IS NULL OR waitlist_position > 0);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_event_presences_waitlist_position
    ON event_presences(event_id, waitlist_position)
    WHERE status = 'WAITLIST' AND waitlist_position IS NOT NULL;

CREATE OR REPLACE FUNCTION rebalance_event_waitlist(p_event_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_max_confirmed_players INTEGER;
    v_confirmed_count INTEGER;
    v_available_slots INTEGER;
BEGIN
    SELECT max_confirmed_players
      INTO v_max_confirmed_players
      FROM pelada_events
     WHERE id = p_event_id
     FOR UPDATE;

    IF v_max_confirmed_players IS NULL THEN
        RETURN;
    END IF;

    -- Mantém os primeiros confirmados e envia os excedentes para o fim da fila.
    WITH ranked_confirmations AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY confirmed_at NULLS FIRST, created_at, id
        ) AS confirmation_order
        FROM event_presences
        WHERE event_id = p_event_id AND status = 'CONFIRMED'
    )
    UPDATE event_presences
       SET status = 'WAITLIST', waitlist_position = NULL
     WHERE id IN (
        SELECT id FROM ranked_confirmations
         WHERE confirmation_order > v_max_confirmed_players
     );

    SELECT COUNT(*)
      INTO v_confirmed_count
      FROM event_presences
     WHERE event_id = p_event_id AND status = 'CONFIRMED';

    v_available_slots := v_max_confirmed_players - v_confirmed_count;

    IF v_available_slots > 0 THEN
        WITH next_in_line AS (
            SELECT id
              FROM event_presences
             WHERE event_id = p_event_id AND status = 'WAITLIST'
             ORDER BY waitlist_position NULLS LAST, created_at, id
             LIMIT v_available_slots
        )
        UPDATE event_presences
           SET status = 'CONFIRMED',
               confirmed_at = COALESCE(confirmed_at, NOW()),
               waitlist_position = NULL
         WHERE id IN (SELECT id FROM next_in_line);
    END IF;

    UPDATE event_presences
       SET waitlist_position = NULL
     WHERE event_id = p_event_id AND status <> 'WAITLIST';

    -- Evita colisão no índice único enquanto a fila recebe posições sequenciais.
    UPDATE event_presences
       SET waitlist_position = waitlist_position + 1000000
     WHERE event_id = p_event_id
       AND status = 'WAITLIST'
       AND waitlist_position IS NOT NULL;

    WITH ranked_waitlist AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY waitlist_position NULLS LAST, created_at, id
        ) AS next_position
        FROM event_presences
        WHERE event_id = p_event_id AND status = 'WAITLIST'
    )
    UPDATE event_presences AS presence
       SET waitlist_position = ranked_waitlist.next_position
      FROM ranked_waitlist
     WHERE presence.id = ranked_waitlist.id;
END;
$$;

CREATE OR REPLACE FUNCTION set_confirmation_time()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'CONFIRMED' AND (
        TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'CONFIRMED'
    ) THEN
        NEW.confirmed_at := NOW();
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION trigger_rebalance_event_waitlist()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'DELETE' THEN
        PERFORM rebalance_event_waitlist(OLD.event_id);
    ELSE
        PERFORM rebalance_event_waitlist(NEW.event_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION validate_event_start()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_confirmed_count INTEGER;
BEGIN
    IF NEW.status = 'IN_PROGRESS' AND (
        TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'IN_PROGRESS'
    ) THEN
        IF NEW.min_confirmed_players IS NULL OR NEW.max_confirmed_players IS NULL THEN
            RAISE EXCEPTION 'Minimum and maximum confirmed players must be configured before starting an event';
        END IF;

        SELECT COUNT(*) INTO v_confirmed_count
          FROM event_presences
         WHERE event_id = NEW.id AND status = 'CONFIRMED';

        IF v_confirmed_count < NEW.min_confirmed_players THEN
            RAISE EXCEPTION 'The event needs at least % confirmed players to start', NEW.min_confirmed_players;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION trigger_rebalance_after_capacity_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.max_confirmed_players IS DISTINCT FROM OLD.max_confirmed_players THEN
        PERFORM rebalance_event_waitlist(NEW.id);
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS before_event_presence_confirmation ON event_presences;
CREATE TRIGGER before_event_presence_confirmation
    BEFORE INSERT OR UPDATE OF status ON event_presences
    FOR EACH ROW EXECUTE FUNCTION set_confirmation_time();

DROP TRIGGER IF EXISTS after_event_presence_rebalance ON event_presences;
CREATE TRIGGER after_event_presence_rebalance
    AFTER INSERT OR UPDATE OR DELETE ON event_presences
    FOR EACH ROW EXECUTE FUNCTION trigger_rebalance_event_waitlist();

DROP TRIGGER IF EXISTS before_event_start_validation ON pelada_events;
CREATE TRIGGER before_event_start_validation
    BEFORE INSERT OR UPDATE OF status ON pelada_events
    FOR EACH ROW EXECUTE FUNCTION validate_event_start();

DROP TRIGGER IF EXISTS after_event_capacity_rebalance ON pelada_events;
CREATE TRIGGER after_event_capacity_rebalance
    AFTER UPDATE OF max_confirmed_players ON pelada_events
    FOR EACH ROW EXECUTE FUNCTION trigger_rebalance_after_capacity_change();
