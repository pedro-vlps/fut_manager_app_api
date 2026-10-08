-- FutManager: esquema completo para um banco NOVO PostgreSQL 17.
-- Gerado pelos modelos atuais e pelo bootstrap da API. Sem usuários ou dados de teste.
-- 1. No servidor PostgreSQL, crie o banco (fora de uma transação):
--    CREATE DATABASE fut_manager WITH ENCODING 'UTF8';
-- 2. Conecte-se ao banco criado e execute este arquivo integralmente.
--    psql -h HOST -U USUARIO -d fut_manager -v ON_ERROR_STOP=1 -f create_database.sql
-- Em serviços gerenciados, use o banco vazio fornecido pelo provedor.
-- Este arquivo NÃO é uma migração para bancos existentes e não deve ser reaplicado.
-- Não contém DROP DATABASE, DROP TABLE nem credenciais.
-- IDs UUID e updated_at são preenchidos/atualizados pela API via SQLAlchemy.

BEGIN;
SET LOCAL search_path TO public;


CREATE TYPE group_role AS ENUM ('OWNER', 'ADMIN', 'MEMBER');

CREATE TYPE membership_status AS ENUM ('ACTIVE', 'INVITED', 'BLOCKED');

CREATE TYPE event_status AS ENUM ('DRAFT', 'REGISTRATION_OPEN', 'REGISTRATION_CLOSED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED');

CREATE TYPE team_player_role AS ENUM ('PLAYER', 'GOALKEEPER');

CREATE TYPE presence_status AS ENUM ('REGISTERED', 'CONFIRMED', 'WAITLIST', 'CANCELLED', 'ABSENT');

CREATE TYPE match_status AS ENUM ('SCHEDULED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED');

CREATE TYPE match_result AS ENUM ('WIN', 'LOSS', 'DRAW');

CREATE TYPE lineup_player_role AS ENUM ('PLAYER', 'GOALKEEPER');

CREATE TYPE game_action_type AS ENUM ('GOAL', 'OWN_GOAL', 'ASSIST', 'YELLOW_CARD', 'RED_CARD');

CREATE TABLE profiles (
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	avatar_url VARCHAR(500), 
	positions JSONB DEFAULT '{}'::jsonb NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_profiles PRIMARY KEY (id), 
	CONSTRAINT uq_profiles_email UNIQUE (email)
);

CREATE TABLE clubs (
	name VARCHAR(80) NOT NULL, 
	owner_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_clubs PRIMARY KEY (id), 
	CONSTRAINT fk_clubs_owner_id_profiles FOREIGN KEY(owner_id) REFERENCES profiles (id)
);

CREATE TABLE pelada_groups (
	code VARCHAR(6) NOT NULL, 
	seasons_enabled BOOLEAN DEFAULT false NOT NULL, 
	season_duration_days INTEGER DEFAULT 30 NOT NULL, 
	season_mode VARCHAR(10) DEFAULT 'days' NOT NULL, 
	season_months INTEGER DEFAULT 3 NOT NULL, 
	season_day INTEGER DEFAULT 10 NOT NULL, 
	season_fixed_end TIMESTAMP WITH TIME ZONE, 
	season_timezone VARCHAR(80) DEFAULT 'America/Sao_Paulo' NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT, 
	created_by_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_pelada_groups PRIMARY KEY (id), 
	CONSTRAINT pelada_groups_code_unique UNIQUE (code), 
	CONSTRAINT fk_pelada_groups_created_by_id_profiles FOREIGN KEY(created_by_id) REFERENCES profiles (id)
);

CREATE TABLE club_members (
	club_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_club_members PRIMARY KEY (id), 
	CONSTRAINT uq_club_members_club_id UNIQUE (club_id, profile_id), 
	CONSTRAINT ck_club_members_club_member_status CHECK (status IN ('pending', 'accepted', 'declined')), 
	CONSTRAINT fk_club_members_club_id_clubs FOREIGN KEY(club_id) REFERENCES clubs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_club_members_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE championships (
	code VARCHAR(6) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	season VARCHAR(80) NOT NULL, 
	description TEXT, 
	owner_id UUID NOT NULL, 
	format VARCHAR(24) NOT NULL, 
	capacity INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	champion_id UUID, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championships PRIMARY KEY (id), 
	CONSTRAINT championships_code_unique UNIQUE (code), 
	CONSTRAINT ck_championships_championship_capacity CHECK (capacity IN (4, 8, 16)), 
	CONSTRAINT ck_championships_cascade_four_teams CHECK (format <> 'cascade' OR capacity = 4), 
	CONSTRAINT ck_championships_championship_format CHECK (format IN ('groups_knockout', 'knockout', 'cascade')), 
	CONSTRAINT ck_championships_championship_status CHECK (status IN ('registration', 'in_progress', 'finished')), 
	CONSTRAINT fk_championships_owner_id_profiles FOREIGN KEY(owner_id) REFERENCES profiles (id), 
	CONSTRAINT fk_championships_champion_id_clubs FOREIGN KEY(champion_id) REFERENCES clubs (id)
);

CREATE TABLE group_draw_settings (
	group_id UUID NOT NULL, 
	use_positions BOOLEAN DEFAULT false NOT NULL, 
	use_ratings BOOLEAN DEFAULT false NOT NULL, 
	use_wins BOOLEAN DEFAULT false NOT NULL, 
	CONSTRAINT pk_group_draw_settings PRIMARY KEY (group_id), 
	CONSTRAINT fk_group_draw_settings_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE
);

CREATE TABLE group_player_ratings (
	group_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	rating NUMERIC(3, 1) NOT NULL, 
	updated_by_id UUID, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_group_player_ratings PRIMARY KEY (id), 
	CONSTRAINT uq_group_player_ratings_group_id UNIQUE (group_id, profile_id), 
	CONSTRAINT ck_group_player_ratings_rating_range CHECK (rating >= 0 AND rating <= 10), 
	CONSTRAINT fk_group_player_ratings_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE, 
	CONSTRAINT fk_group_player_ratings_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_group_player_ratings_updated_by_id_profiles FOREIGN KEY(updated_by_id) REFERENCES profiles (id) ON DELETE SET NULL
);

CREATE TABLE group_seasons (
	group_id UUID NOT NULL, 
	number INTEGER NOT NULL, 
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	archived_rankings JSONB, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_group_seasons PRIMARY KEY (id), 
	CONSTRAINT uq_group_seasons_group_id UNIQUE (group_id, number), 
	CONSTRAINT ck_group_seasons_season_positive_period CHECK (ends_at > starts_at), 
	CONSTRAINT fk_group_seasons_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE
);

CREATE TABLE group_members (
	group_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	role group_role NOT NULL, 
	status membership_status NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_group_members PRIMARY KEY (id), 
	CONSTRAINT uq_group_members_group_id UNIQUE (group_id, profile_id), 
	CONSTRAINT fk_group_members_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE, 
	CONSTRAINT fk_group_members_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE group_join_requests (
	group_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	status VARCHAR(16) DEFAULT 'pending' NOT NULL, 
	reviewed_by_id UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_group_join_requests PRIMARY KEY (id), 
	CONSTRAINT uq_group_join_requests_group_id UNIQUE (group_id, profile_id), 
	CONSTRAINT ck_group_join_requests_join_request_status CHECK (status IN ('pending', 'approved', 'rejected')), 
	CONSTRAINT fk_group_join_requests_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE, 
	CONSTRAINT fk_group_join_requests_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id), 
	CONSTRAINT fk_group_join_requests_reviewed_by_id_profiles FOREIGN KEY(reviewed_by_id) REFERENCES profiles (id)
);

CREATE TABLE group_guests (
	group_id UUID NOT NULL, 
	created_by_id UUID NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_group_guests PRIMARY KEY (id), 
	CONSTRAINT fk_group_guests_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE, 
	CONSTRAINT fk_group_guests_created_by_id_profiles FOREIGN KEY(created_by_id) REFERENCES profiles (id)
);

CREATE TABLE pelada_events (
	group_id UUID NOT NULL, 
	created_by_id UUID NOT NULL, 
	title VARCHAR(150) NOT NULL, 
	location VARCHAR(255), 
	scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	modality VARCHAR(10), 
	recurring_weekly BOOLEAN DEFAULT false NOT NULL, 
	schedule_timezone VARCHAR(80) DEFAULT 'America/Sao_Paulo' NOT NULL, 
	recurrence_parent_id UUID, 
	registration_opens_at TIMESTAMP WITH TIME ZONE, 
	registration_closes_at TIMESTAMP WITH TIME ZONE, 
	min_confirmed_players INTEGER, 
	max_confirmed_players INTEGER, 
	min_confirmed_goalkeepers INTEGER, 
	max_confirmed_goalkeepers INTEGER, 
	match_duration_minutes INTEGER, 
	status event_status NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_pelada_events PRIMARY KEY (id), 
	CONSTRAINT ck_pelada_events_positive_max_confirmed_players CHECK (max_confirmed_players IS NULL OR max_confirmed_players > 0), 
	CONSTRAINT ck_pelada_events_positive_min_confirmed_players CHECK (min_confirmed_players IS NULL OR min_confirmed_players > 0), 
	CONSTRAINT ck_pelada_events_min_confirmed_not_greater_than_max CHECK (min_confirmed_players IS NULL OR max_confirmed_players IS NULL OR min_confirmed_players <= max_confirmed_players), 
	CONSTRAINT ck_pelada_events_positive_match_duration CHECK (match_duration_minutes IS NULL OR match_duration_minutes > 0), 
	CONSTRAINT fk_pelada_events_group_id_pelada_groups FOREIGN KEY(group_id) REFERENCES pelada_groups (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pelada_events_created_by_id_profiles FOREIGN KEY(created_by_id) REFERENCES profiles (id), 
	CONSTRAINT uq_pelada_events_recurrence_parent_id UNIQUE (recurrence_parent_id), 
	CONSTRAINT fk_pelada_events_recurrence_parent_id_pelada_events FOREIGN KEY(recurrence_parent_id) REFERENCES pelada_events (id) ON DELETE SET NULL
);

CREATE INDEX ix_pelada_events_group_scheduled_at ON pelada_events (group_id, scheduled_at);

CREATE TABLE championship_entries (
	championship_id UUID NOT NULL, 
	club_id UUID NOT NULL, 
	seed INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_entries PRIMARY KEY (id), 
	CONSTRAINT uq_championship_entries_championship_id UNIQUE (championship_id, club_id), 
	CONSTRAINT fk_championship_entries_championship_id_championships FOREIGN KEY(championship_id) REFERENCES championships (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_entries_club_id_clubs FOREIGN KEY(club_id) REFERENCES clubs (id)
);

CREATE TABLE championship_matches (
	championship_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	stage VARCHAR(16) NOT NULL, 
	round INTEGER NOT NULL, 
	pool VARCHAR(1), 
	home_id UUID NOT NULL, 
	away_id UUID NOT NULL, 
	home_score INTEGER, 
	away_score INTEGER, 
	winner_id UUID, 
	statistics_complete BOOLEAN DEFAULT false NOT NULL, 
	actions JSONB DEFAULT '[]'::jsonb NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_matches PRIMARY KEY (id), 
	CONSTRAINT uq_championship_matches_championship_id UNIQUE (championship_id, sequence), 
	CONSTRAINT ck_championship_matches_different_clubs CHECK (home_id <> away_id), 
	CONSTRAINT ck_championship_matches_positive_scores CHECK (home_score >= 0 AND away_score >= 0), 
	CONSTRAINT fk_championship_matches_championship_id_championships FOREIGN KEY(championship_id) REFERENCES championships (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_matches_home_id_clubs FOREIGN KEY(home_id) REFERENCES clubs (id), 
	CONSTRAINT fk_championship_matches_away_id_clubs FOREIGN KEY(away_id) REFERENCES clubs (id), 
	CONSTRAINT fk_championship_matches_winner_id_clubs FOREIGN KEY(winner_id) REFERENCES clubs (id)
);

CREATE TABLE championship_trophies (
	championship_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	category VARCHAR(40) NOT NULL, 
	title VARCHAR(350) NOT NULL, 
	value INTEGER NOT NULL, 
	awarded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_trophies PRIMARY KEY (id), 
	CONSTRAINT uq_championship_trophies_championship_id UNIQUE (championship_id, profile_id, category), 
	CONSTRAINT fk_championship_trophies_championship_id_championships FOREIGN KEY(championship_id) REFERENCES championships (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_trophies_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE season_trophies (
	season_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	title VARCHAR(250) NOT NULL, 
	value INTEGER NOT NULL, 
	awarded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_season_trophies PRIMARY KEY (id), 
	CONSTRAINT uq_season_trophies_season_id UNIQUE (season_id, profile_id, category), 
	CONSTRAINT fk_season_trophies_season_id_group_seasons FOREIGN KEY(season_id) REFERENCES group_seasons (id) ON DELETE CASCADE, 
	CONSTRAINT fk_season_trophies_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE event_presences (
	role team_player_role DEFAULT 'PLAYER' NOT NULL, 
	event_id UUID NOT NULL, 
	profile_id UUID, 
	guest_id UUID, 
	status presence_status NOT NULL, 
	waitlist_position INTEGER, 
	confirmed_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_event_presences PRIMARY KEY (id), 
	CONSTRAINT uq_event_presence_profile UNIQUE (event_id, profile_id), 
	CONSTRAINT uq_event_presence_guest UNIQUE (event_id, guest_id), 
	CONSTRAINT ck_event_presences_positive_waitlist_position CHECK (waitlist_position IS NULL OR waitlist_position > 0), 
	CONSTRAINT ck_event_presences_profile_or_guest_presence CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL)), 
	CONSTRAINT fk_event_presences_event_id_pelada_events FOREIGN KEY(event_id) REFERENCES pelada_events (id) ON DELETE CASCADE, 
	CONSTRAINT fk_event_presences_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id), 
	CONSTRAINT fk_event_presences_guest_id_group_guests FOREIGN KEY(guest_id) REFERENCES group_guests (id) ON DELETE CASCADE
);

CREATE INDEX ix_event_presences_event_status ON event_presences (event_id, status);

CREATE UNIQUE INDEX uq_event_presences_waitlist_position ON event_presences (event_id, waitlist_position) WHERE status = 'WAITLIST' AND waitlist_position IS NOT NULL;

CREATE TABLE event_teams (
	event_id UUID NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	color VARCHAR(7), 
	draw_order INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_event_teams PRIMARY KEY (id), 
	CONSTRAINT uq_event_teams_event_id UNIQUE (event_id, name), 
	CONSTRAINT fk_event_teams_event_id_pelada_events FOREIGN KEY(event_id) REFERENCES pelada_events (id) ON DELETE CASCADE
);

CREATE TABLE championship_players (
	championship_id UUID NOT NULL, 
	entry_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_players PRIMARY KEY (id), 
	CONSTRAINT uq_championship_players_championship_id UNIQUE (championship_id, profile_id), 
	CONSTRAINT fk_championship_players_championship_id_championships FOREIGN KEY(championship_id) REFERENCES championships (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_players_entry_id_championship_entries FOREIGN KEY(entry_id) REFERENCES championship_entries (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_players_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE championship_statistics (
	match_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	goals INTEGER NOT NULL, 
	assists INTEGER NOT NULL, 
	own_goals INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_statistics PRIMARY KEY (id), 
	CONSTRAINT uq_championship_statistics_match_id UNIQUE (match_id, profile_id), 
	CONSTRAINT ck_championship_statistics_nonnegative_statistics CHECK (goals >= 0 AND assists >= 0 AND own_goals >= 0), 
	CONSTRAINT fk_championship_statistics_match_id_championship_matches FOREIGN KEY(match_id) REFERENCES championship_matches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_statistics_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
);

CREATE TABLE event_team_players (
	team_id UUID NOT NULL, 
	profile_id UUID, 
	guest_id UUID, 
	role team_player_role NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_event_team_players PRIMARY KEY (id), 
	CONSTRAINT uq_event_team_player_profile UNIQUE (team_id, profile_id), 
	CONSTRAINT uq_event_team_player_guest UNIQUE (team_id, guest_id), 
	CONSTRAINT ck_event_team_players_profile_or_guest_team_player CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL)), 
	CONSTRAINT fk_event_team_players_team_id_event_teams FOREIGN KEY(team_id) REFERENCES event_teams (id) ON DELETE CASCADE, 
	CONSTRAINT fk_event_team_players_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id), 
	CONSTRAINT fk_event_team_players_guest_id_group_guests FOREIGN KEY(guest_id) REFERENCES group_guests (id) ON DELETE CASCADE
);

CREATE TABLE event_team_queue_entries (
	event_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	position INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_event_team_queue_entries PRIMARY KEY (id), 
	CONSTRAINT uq_event_team_queue_event_team UNIQUE (event_id, team_id), 
	CONSTRAINT uq_event_team_queue_event_position UNIQUE (event_id, position), 
	CONSTRAINT ck_event_team_queue_entries_positive_queue_position CHECK (position > 0), 
	CONSTRAINT fk_event_team_queue_entries_event_id_pelada_events FOREIGN KEY(event_id) REFERENCES pelada_events (id) ON DELETE CASCADE, 
	CONSTRAINT fk_event_team_queue_entries_team_id_event_teams FOREIGN KEY(team_id) REFERENCES event_teams (id) ON DELETE CASCADE
);

CREATE TABLE matches (
	event_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	previous_match_id UUID, 
	advancing_team_id UUID, 
	status match_status NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	timer_elapsed_ms INTEGER DEFAULT 0 NOT NULL, 
	timer_running_since TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_matches PRIMARY KEY (id), 
	CONSTRAINT uq_matches_event_id UNIQUE (event_id, sequence), 
	CONSTRAINT uq_matches_previous_match_id UNIQUE (previous_match_id), 
	CONSTRAINT fk_matches_event_id_pelada_events FOREIGN KEY(event_id) REFERENCES pelada_events (id) ON DELETE CASCADE, 
	CONSTRAINT fk_matches_previous_match_id_matches FOREIGN KEY(previous_match_id) REFERENCES matches (id), 
	CONSTRAINT fk_matches_advancing_team_id_event_teams FOREIGN KEY(advancing_team_id) REFERENCES event_teams (id)
);

CREATE INDEX ix_matches_event_started_at ON matches (event_id, started_at);

CREATE TABLE match_teams (
	match_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	goals INTEGER NOT NULL, 
	result match_result, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_match_teams PRIMARY KEY (id), 
	CONSTRAINT uq_match_teams_match_id UNIQUE (match_id, team_id), 
	CONSTRAINT fk_match_teams_match_id_matches FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_match_teams_team_id_event_teams FOREIGN KEY(team_id) REFERENCES event_teams (id)
);

CREATE TABLE match_lineups (
	is_active BOOLEAN DEFAULT true NOT NULL, 
	replaced_lineup_id UUID, 
	match_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	profile_id UUID, 
	guest_id UUID, 
	role lineup_player_role NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_match_lineups PRIMARY KEY (id), 
	CONSTRAINT uq_match_lineup_profile UNIQUE (match_id, profile_id), 
	CONSTRAINT uq_match_lineup_guest UNIQUE (match_id, guest_id), 
	CONSTRAINT ck_match_lineups_profile_or_guest_match_lineup CHECK ((profile_id IS NOT NULL AND guest_id IS NULL) OR (profile_id IS NULL AND guest_id IS NOT NULL)), 
	CONSTRAINT fk_match_lineups_replaced_lineup_id_match_lineups FOREIGN KEY(replaced_lineup_id) REFERENCES match_lineups (id), 
	CONSTRAINT fk_match_lineups_match_id_matches FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_match_lineups_team_id_event_teams FOREIGN KEY(team_id) REFERENCES event_teams (id), 
	CONSTRAINT fk_match_lineups_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id), 
	CONSTRAINT fk_match_lineups_guest_id_group_guests FOREIGN KEY(guest_id) REFERENCES group_guests (id) ON DELETE CASCADE
);

CREATE TABLE game_actions (
	match_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	player_id UUID, 
	guest_id UUID, 
	action_type game_action_type NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE, 
	minute INTEGER, 
	notes VARCHAR(500), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_game_actions PRIMARY KEY (id), 
	CONSTRAINT ck_game_actions_profile_or_guest_game_action CHECK ((player_id IS NOT NULL AND guest_id IS NULL) OR (player_id IS NULL AND guest_id IS NOT NULL)), 
	CONSTRAINT fk_game_actions_match_id_matches FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_game_actions_team_id_event_teams FOREIGN KEY(team_id) REFERENCES event_teams (id), 
	CONSTRAINT fk_game_actions_player_id_profiles FOREIGN KEY(player_id) REFERENCES profiles (id), 
	CONSTRAINT fk_game_actions_guest_id_group_guests FOREIGN KEY(guest_id) REFERENCES group_guests (id) ON DELETE CASCADE
);

CREATE INDEX ix_game_actions_match_type ON game_actions (match_id, action_type);


-- Complemento: migrations/007_group_alpha_numeric_code.sql
-- Código público do grupo: seis caracteres A-Z/0-9, gerados pelo PostgreSQL.
-- A sequência e a permutação bijetiva evitam colisões, inclusive em concorrência.
-- 36^6 = 2.176.782.336 códigos; a sequência nunca reutiliza valores.
CREATE SEQUENCE IF NOT EXISTS group_code_sequence
    AS BIGINT MINVALUE 0 MAXVALUE 2176782335 START WITH 0 NO CYCLE;

ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS code VARCHAR(6);

CREATE OR REPLACE FUNCTION generate_group_code()
RETURNS VARCHAR(6)
LANGUAGE plpgsql VOLATILE
AS $$
DECLARE
    alphabet CONSTANT TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    value BIGINT;
    generated TEXT;
BEGIN
    LOOP
        value := (nextval('group_code_sequence') * 7919 + 104729) % 2176782336;
        generated := '';
        FOR digit IN 1..6 LOOP
            generated := substr(alphabet, (value % 36)::INTEGER + 1, 1) || generated;
            value := value / 36;
        END LOOP;
        EXIT WHEN NOT EXISTS (SELECT 1 FROM pelada_groups WHERE code = generated);
    END LOOP;
    RETURN generated;
END;
$$;

UPDATE pelada_groups SET code = generate_group_code() WHERE code IS NULL;
ALTER TABLE pelada_groups ALTER COLUMN code SET DEFAULT generate_group_code();
ALTER TABLE pelada_groups ALTER COLUMN code SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'pelada_groups'::regclass AND conname = 'pelada_groups_code_unique') THEN
        ALTER TABLE pelada_groups ADD CONSTRAINT pelada_groups_code_unique UNIQUE (code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'pelada_groups'::regclass AND conname = 'pelada_groups_code_format') THEN
        ALTER TABLE pelada_groups ADD CONSTRAINT pelada_groups_code_format CHECK (code ~ '^[A-Z0-9]{6}$');
    END IF;
END;
$$;



-- Complemento: migrations/009_group_seasons.sql
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



-- Complemento: migrations/010_season_trophies.sql
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



-- Complemento: migrations/011_event_schedule.sql
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS recurring_weekly boolean NOT NULL DEFAULT false;
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS schedule_timezone varchar(80) NOT NULL DEFAULT 'America/Sao_Paulo';
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS recurrence_parent_id uuid REFERENCES pelada_events(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_recurrence_parent ON pelada_events(recurrence_parent_id);



-- Complemento: migrations/012_season_calendar.sql
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_mode varchar(10) NOT NULL DEFAULT 'days';
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_months integer NOT NULL DEFAULT 3;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_day integer NOT NULL DEFAULT 10;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_fixed_end timestamptz;
ALTER TABLE pelada_groups ADD COLUMN IF NOT EXISTS season_timezone varchar(80) NOT NULL DEFAULT 'America/Sao_Paulo';



-- Complemento: migrations/013_event_modality.sql
ALTER TABLE pelada_events ADD COLUMN IF NOT EXISTS modality varchar(10);



-- Complemento: migrations/014_goalkeeper_confirmations.sql
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



-- Complemento: migrations/015_temporary_substitutions.sql
-- Preserve past lineups and actions. New substitutions mark the outgoing player inactive.
ALTER TABLE match_lineups ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE match_lineups ADD COLUMN IF NOT EXISTS replaced_lineup_id uuid REFERENCES match_lineups(id);



-- Complemento: migrations/016_draw_settings_and_ratings.sql
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



-- Complemento: migrations/018_cascade_trophies.sql
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS statistics_complete BOOLEAN NOT NULL DEFAULT false;
-- NOT VALID preserva edições antigas de cascata com 8/16 vagas, que não podem
-- iniciar. Novas edições e alterações precisam respeitar o limite de 4.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_championships_cascade_four_teams'
                   AND conrelid = 'championships'::regclass) THEN
        ALTER TABLE championships ADD CONSTRAINT ck_championships_cascade_four_teams
            CHECK (format <> 'cascade' OR capacity = 4) NOT VALID;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS championship_statistics (
	match_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	goals INTEGER NOT NULL, 
	assists INTEGER NOT NULL, 
	own_goals INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_statistics PRIMARY KEY (id), 
	CONSTRAINT uq_championship_statistics_match_id UNIQUE (match_id, profile_id), 
	CONSTRAINT ck_championship_statistics_nonnegative_statistics CHECK (goals >= 0 AND assists >= 0 AND own_goals >= 0), 
	CONSTRAINT fk_championship_statistics_match_id_championship_matches FOREIGN KEY(match_id) REFERENCES championship_matches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_statistics_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
)

;

CREATE TABLE IF NOT EXISTS championship_trophies (
	championship_id UUID NOT NULL, 
	profile_id UUID NOT NULL, 
	category VARCHAR(40) NOT NULL, 
	title VARCHAR(350) NOT NULL, 
	value INTEGER NOT NULL, 
	awarded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_championship_trophies PRIMARY KEY (id), 
	CONSTRAINT uq_championship_trophies_championship_id UNIQUE (championship_id, profile_id, category), 
	CONSTRAINT fk_championship_trophies_championship_id_championships FOREIGN KEY(championship_id) REFERENCES championships (id) ON DELETE CASCADE, 
	CONSTRAINT fk_championship_trophies_profile_id_profiles FOREIGN KEY(profile_id) REFERENCES profiles (id)
)

;



-- Complemento: migrations/019_championship_codes.sql
-- Código público do campeonato: seis caracteres A-Z/0-9, gerados pelo PostgreSQL.
-- A sequência e a permutação bijetiva evitam colisões, inclusive em concorrência.
-- 36^6 = 2.176.782.336 códigos; a sequência nunca reutiliza valores.
CREATE SEQUENCE IF NOT EXISTS championship_code_sequence
    AS BIGINT MINVALUE 0 MAXVALUE 2176782335 START WITH 0 NO CYCLE;

ALTER TABLE championships ADD COLUMN IF NOT EXISTS code VARCHAR(6);

CREATE OR REPLACE FUNCTION generate_championship_code()
RETURNS VARCHAR(6)
LANGUAGE plpgsql VOLATILE
AS $$
DECLARE
    alphabet CONSTANT TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    value BIGINT;
    generated TEXT;
BEGIN
    LOOP
        value := (nextval('championship_code_sequence') * 7919 + 104729) % 2176782336;
        generated := '';
        FOR digit IN 1..6 LOOP
            generated := substr(alphabet, (value % 36)::INTEGER + 1, 1) || generated;
            value := value / 36;
        END LOOP;
        EXIT WHEN NOT EXISTS (SELECT 1 FROM championships WHERE code = generated);
    END LOOP;
    RETURN generated;
END;
$$;

UPDATE championships SET code = generate_championship_code() WHERE code IS NULL;
ALTER TABLE championships ALTER COLUMN code SET DEFAULT generate_championship_code();
ALTER TABLE championships ALTER COLUMN code SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'championships'::regclass AND conname = 'championships_code_unique') THEN
        ALTER TABLE championships ADD CONSTRAINT championships_code_unique UNIQUE (code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'championships'::regclass AND conname = 'championships_code_format') THEN
        ALTER TABLE championships ADD CONSTRAINT championships_code_format CHECK (code ~ '^[A-Z0-9]{6}$');
    END IF;
END;
$$;



-- Complemento: migrations/020_championship_actions.sql
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS actions JSONB NOT NULL DEFAULT '[]'::jsonb;



COMMIT;
