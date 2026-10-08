-- Estrutura aditiva dos campeonatos sazonais.
BEGIN;

CREATE TABLE IF NOT EXISTS clubs (
	name VARCHAR(80) NOT NULL, 
	owner_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_clubs PRIMARY KEY (id), 
	CONSTRAINT fk_clubs_owner_id_profiles FOREIGN KEY(owner_id) REFERENCES profiles (id)
)

;

CREATE TABLE IF NOT EXISTS club_members (
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
)

;

CREATE TABLE IF NOT EXISTS championships (
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
	CONSTRAINT ck_championships_championship_capacity CHECK (capacity IN (4, 8, 16)), 
	CONSTRAINT ck_championships_championship_format CHECK (format IN ('groups_knockout', 'knockout', 'cascade')), 
	CONSTRAINT ck_championships_championship_status CHECK (status IN ('registration', 'in_progress', 'finished')), 
	CONSTRAINT fk_championships_owner_id_profiles FOREIGN KEY(owner_id) REFERENCES profiles (id), 
	CONSTRAINT fk_championships_champion_id_clubs FOREIGN KEY(champion_id) REFERENCES clubs (id)
)

;

CREATE TABLE IF NOT EXISTS championship_entries (
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
)

;

CREATE TABLE IF NOT EXISTS championship_players (
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
)

;

CREATE TABLE IF NOT EXISTS championship_matches (
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
)

;
COMMIT;
