ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS min_confirmed_goalkeepers integer;
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS max_confirmed_goalkeepers integer;
ALTER TABLE event_presences ADD COLUMN IF NOT EXISTS role team_player_role NOT NULL DEFAULT 'PLAYER';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_event_goalkeeper_limits') THEN
        ALTER TABLE pelada_events ADD CONSTRAINT ck_event_goalkeeper_limits CHECK (
            (min_confirmed_goalkeepers IS NULL AND max_confirmed_goalkeepers IS NULL) OR
            (min_confirmed_goalkeepers IS NOT NULL AND min_confirmed_goalkeepers BETWEEN 0 AND 4
             AND (max_confirmed_goalkeepers IS NULL OR
                  max_confirmed_goalkeepers BETWEEN min_confirmed_goalkeepers AND 4))
        );
    END IF;
END $$;

CREATE OR REPLACE FUNCTION set_confirmation_time()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'CONFIRMED' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'CONFIRMED') THEN
        NEW.confirmed_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS before_event_presence_confirmation ON event_presences;
CREATE TRIGGER before_event_presence_confirmation BEFORE INSERT OR UPDATE OF status ON event_presences
    FOR EACH ROW EXECUTE FUNCTION set_confirmation_time();

-- Existing events retain their combined capacity until separate slots are configured.
CREATE OR REPLACE FUNCTION rebalance_event_waitlist(p_event_id UUID)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_event pelada_events%ROWTYPE;
    v_role team_player_role;
    v_limit integer;
    v_count integer;
BEGIN
    SELECT * INTO v_event FROM pelada_events WHERE id = p_event_id FOR UPDATE;
    FOREACH v_role IN ARRAY ARRAY['PLAYER', 'GOALKEEPER']::team_player_role[] LOOP
        IF v_event.min_confirmed_goalkeepers IS NULL AND v_role = 'GOALKEEPER' THEN EXIT; END IF;
        v_limit := CASE WHEN v_role = 'GOALKEEPER' THEN v_event.max_confirmed_goalkeepers
                        ELSE v_event.max_confirmed_players END;
        IF v_limit IS NOT NULL THEN
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY (guest_id IS NOT NULL), confirmed_at NULLS FIRST, created_at, id
                ) AS n FROM event_presences
                WHERE event_id = p_event_id AND status = 'CONFIRMED'
                  AND (v_event.min_confirmed_goalkeepers IS NULL OR role = v_role)
            ) UPDATE event_presences SET status = 'WAITLIST', waitlist_position = NULL
              WHERE id IN (SELECT id FROM ranked WHERE n > v_limit);
        END IF;
        SELECT COUNT(*) INTO v_count FROM event_presences
          WHERE event_id = p_event_id AND status = 'CONFIRMED'
            AND (v_event.min_confirmed_goalkeepers IS NULL OR role = v_role);
        WITH next_in_line AS (
            SELECT id FROM event_presences
            WHERE event_id = p_event_id AND status = 'WAITLIST'
              AND (v_event.min_confirmed_goalkeepers IS NULL OR role = v_role)
            ORDER BY (guest_id IS NOT NULL), waitlist_position NULLS LAST, created_at, id
            LIMIT CASE WHEN v_limit IS NULL THEN NULL ELSE GREATEST(0, v_limit - v_count) END
        ) UPDATE event_presences SET status = 'CONFIRMED',
            confirmed_at = COALESCE(confirmed_at, NOW()), waitlist_position = NULL
          WHERE id IN (SELECT id FROM next_in_line);
    END LOOP;
    UPDATE event_presences SET waitlist_position = NULL
      WHERE event_id = p_event_id AND status <> 'WAITLIST' AND waitlist_position IS NOT NULL;
    UPDATE event_presences SET waitlist_position = waitlist_position + 1000000
      WHERE event_id = p_event_id AND status = 'WAITLIST' AND waitlist_position IS NOT NULL;
    WITH ranked AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY (guest_id IS NOT NULL), waitlist_position NULLS LAST, created_at, id
        ) AS n FROM event_presences WHERE event_id = p_event_id AND status = 'WAITLIST'
    ) UPDATE event_presences AS p SET waitlist_position = ranked.n FROM ranked WHERE p.id = ranked.id;
END $$;

CREATE OR REPLACE FUNCTION trigger_rebalance_event_waitlist()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN RETURN NULL; END IF;
    IF TG_OP = 'DELETE' THEN
        PERFORM rebalance_event_waitlist(OLD.event_id);
    ELSE
        PERFORM rebalance_event_waitlist(NEW.event_id);
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS after_event_presence_rebalance ON event_presences;
CREATE TRIGGER after_event_presence_rebalance AFTER INSERT OR UPDATE OR DELETE ON event_presences
    FOR EACH ROW EXECUTE FUNCTION trigger_rebalance_event_waitlist();

CREATE OR REPLACE FUNCTION trigger_rebalance_after_capacity_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.max_confirmed_players, NEW.min_confirmed_goalkeepers, NEW.max_confirmed_goalkeepers)
       IS DISTINCT FROM (OLD.max_confirmed_players, OLD.min_confirmed_goalkeepers, OLD.max_confirmed_goalkeepers) THEN
        PERFORM rebalance_event_waitlist(NEW.id);
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS after_event_capacity_rebalance ON pelada_events;
CREATE TRIGGER after_event_capacity_rebalance
    AFTER UPDATE OF max_confirmed_players, min_confirmed_goalkeepers, max_confirmed_goalkeepers ON pelada_events
    FOR EACH ROW EXECUTE FUNCTION trigger_rebalance_after_capacity_change();

CREATE OR REPLACE FUNCTION validate_event_start()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_players integer; v_keepers integer;
BEGIN
    IF NEW.status = 'IN_PROGRESS' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'IN_PROGRESS') THEN
        SELECT COUNT(*) FILTER (WHERE NEW.min_confirmed_goalkeepers IS NULL OR role = 'PLAYER'),
               COUNT(*) FILTER (WHERE role = 'GOALKEEPER')
          INTO v_players, v_keepers FROM event_presences WHERE event_id = NEW.id AND status = 'CONFIRMED';
        IF v_players < GREATEST(3, COALESCE(NEW.min_confirmed_players, 0)) THEN
            RAISE EXCEPTION 'Insufficient confirmed players';
        END IF;
        IF v_keepers < COALESCE(NEW.min_confirmed_goalkeepers, 0) THEN
            RAISE EXCEPTION 'Insufficient confirmed goalkeepers';
        END IF;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS before_event_start_validation ON pelada_events;
CREATE TRIGGER before_event_start_validation BEFORE INSERT OR UPDATE OF status ON pelada_events
    FOR EACH ROW EXECUTE FUNCTION validate_event_start();
