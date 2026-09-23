-- Convidados sem perfil: pertencem a um grupo e podem participar de eventos.
CREATE TABLE IF NOT EXISTS group_guests (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    group_id UUID NOT NULL REFERENCES pelada_groups(id) ON DELETE CASCADE,
    created_by_id UUID NOT NULL REFERENCES profiles(id),
    name VARCHAR(120) NOT NULL
);

ALTER TABLE event_presences
    ALTER COLUMN profile_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS guest_id UUID REFERENCES group_guests(id) ON DELETE CASCADE;

ALTER TABLE event_team_players
    ALTER COLUMN profile_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS guest_id UUID REFERENCES group_guests(id) ON DELETE CASCADE;

ALTER TABLE match_lineups
    ALTER COLUMN profile_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS guest_id UUID REFERENCES group_guests(id) ON DELETE CASCADE;

ALTER TABLE game_actions
    ALTER COLUMN player_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS guest_id UUID REFERENCES group_guests(id) ON DELETE CASCADE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_event_presence_guest') THEN
        ALTER TABLE event_presences ADD CONSTRAINT uq_event_presence_guest UNIQUE (event_id, guest_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_event_presences_profile_or_guest_presence') THEN
        ALTER TABLE event_presences ADD CONSTRAINT ck_event_presences_profile_or_guest_presence
            CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_event_team_player_guest') THEN
        ALTER TABLE event_team_players ADD CONSTRAINT uq_event_team_player_guest UNIQUE (team_id, guest_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_event_team_players_profile_or_guest_team_player') THEN
        ALTER TABLE event_team_players ADD CONSTRAINT ck_event_team_players_profile_or_guest_team_player
            CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_match_lineup_guest') THEN
        ALTER TABLE match_lineups ADD CONSTRAINT uq_match_lineup_guest UNIQUE (match_id, guest_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_match_lineups_profile_or_guest_match_lineup') THEN
        ALTER TABLE match_lineups ADD CONSTRAINT ck_match_lineups_profile_or_guest_match_lineup
            CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_game_actions_profile_or_guest_game_action') THEN
        ALTER TABLE game_actions ADD CONSTRAINT ck_game_actions_profile_or_guest_game_action
            CHECK ((player_id IS NOT NULL AND guest_id IS NULL) OR (player_id IS NULL AND guest_id IS NOT NULL));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION validate_group_guest_creator()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM group_members
         WHERE group_id = NEW.group_id
           AND profile_id = NEW.created_by_id
           AND status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'Only an active group member can add a guest';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_guest_event_presence()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.guest_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
          FROM group_guests AS guest
          JOIN pelada_events AS event ON event.group_id = guest.group_id
         WHERE guest.id = NEW.guest_id AND event.id = NEW.event_id
    ) THEN
        RAISE EXCEPTION 'The guest must belong to the event group';
    END IF;
    RETURN NEW;
END;
$$;

-- Perfis têm prioridade sobre convidados tanto entre confirmados quanto na espera.
CREATE OR REPLACE FUNCTION rebalance_event_waitlist(p_event_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_max_confirmed_players INTEGER;
    v_confirmed_count INTEGER;
    v_available_slots INTEGER;
BEGIN
    SELECT max_confirmed_players INTO v_max_confirmed_players
      FROM pelada_events WHERE id = p_event_id FOR UPDATE;
    IF v_max_confirmed_players IS NULL THEN RETURN; END IF;

    WITH ranked_confirmations AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY (guest_id IS NOT NULL), confirmed_at NULLS FIRST, created_at, id
        ) AS confirmation_order
        FROM event_presences
        WHERE event_id = p_event_id AND status = 'CONFIRMED'
    )
    UPDATE event_presences SET status = 'WAITLIST', waitlist_position = NULL
     WHERE id IN (SELECT id FROM ranked_confirmations WHERE confirmation_order > v_max_confirmed_players);

    SELECT COUNT(*) INTO v_confirmed_count FROM event_presences
     WHERE event_id = p_event_id AND status = 'CONFIRMED';
    v_available_slots := v_max_confirmed_players - v_confirmed_count;

    IF v_available_slots > 0 THEN
        WITH next_in_line AS (
            SELECT id FROM event_presences
             WHERE event_id = p_event_id AND status = 'WAITLIST'
             ORDER BY (guest_id IS NOT NULL), waitlist_position NULLS LAST, created_at, id
             LIMIT v_available_slots
        )
        UPDATE event_presences
           SET status = 'CONFIRMED', confirmed_at = COALESCE(confirmed_at, NOW()), waitlist_position = NULL
         WHERE id IN (SELECT id FROM next_in_line);
    END IF;

    UPDATE event_presences SET waitlist_position = NULL
     WHERE event_id = p_event_id AND status <> 'WAITLIST';
    UPDATE event_presences SET waitlist_position = waitlist_position + 1000000
     WHERE event_id = p_event_id AND status = 'WAITLIST' AND waitlist_position IS NOT NULL;

    WITH ranked_waitlist AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY (guest_id IS NOT NULL), waitlist_position NULLS LAST, created_at, id
        ) AS next_position
        FROM event_presences WHERE event_id = p_event_id AND status = 'WAITLIST'
    )
    UPDATE event_presences AS presence SET waitlist_position = ranked_waitlist.next_position
      FROM ranked_waitlist WHERE presence.id = ranked_waitlist.id;
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

DROP TRIGGER IF EXISTS before_event_presence_confirmation ON event_presences;
CREATE TRIGGER before_event_presence_confirmation
    BEFORE INSERT OR UPDATE OF status ON event_presences
    FOR EACH ROW EXECUTE FUNCTION set_confirmation_time();

DROP TRIGGER IF EXISTS after_event_presence_rebalance ON event_presences;
CREATE TRIGGER after_event_presence_rebalance
    AFTER INSERT OR UPDATE OR DELETE ON event_presences
    FOR EACH ROW EXECUTE FUNCTION trigger_rebalance_event_waitlist();

DROP TRIGGER IF EXISTS before_group_guest_creator_validation ON group_guests;
CREATE TRIGGER before_group_guest_creator_validation
    BEFORE INSERT OR UPDATE OF group_id, created_by_id ON group_guests
    FOR EACH ROW EXECUTE FUNCTION validate_group_guest_creator();

DROP TRIGGER IF EXISTS before_guest_event_presence_validation ON event_presences;
CREATE TRIGGER before_guest_event_presence_validation
    BEFORE INSERT OR UPDATE OF event_id, guest_id ON event_presences
    FOR EACH ROW EXECUTE FUNCTION validate_guest_event_presence();
