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
