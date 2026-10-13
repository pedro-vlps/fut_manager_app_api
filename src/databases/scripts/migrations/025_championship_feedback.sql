BEGIN;
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_championship_capacity;
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_twelve_teams_groups;
ALTER TABLE championships ADD CONSTRAINT ck_championships_championship_capacity
 CHECK ((format = 'league' AND capacity >= 2) OR (format <> 'league' AND capacity IN (4,8,12,16)));
ALTER TABLE championships ADD CONSTRAINT ck_championships_twelve_teams_groups
 CHECK (capacity <> 12 OR format IN ('groups_knockout', 'league'));
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS disqualified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS points_deducted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS punishments JSONB NOT NULL DEFAULT '[]';
ALTER TABLE championship_matches ADD COLUMN IF NOT EXISTS walkover BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS code VARCHAR(6);
CREATE SEQUENCE IF NOT EXISTS club_code_sequence AS BIGINT MINVALUE 0 MAXVALUE 2176782335 START WITH 0 NO CYCLE;
CREATE OR REPLACE FUNCTION generate_club_code() RETURNS VARCHAR(6) LANGUAGE plpgsql VOLATILE AS $$
DECLARE alphabet CONSTANT TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; value BIGINT; generated TEXT;
BEGIN
 LOOP
  value := (nextval('club_code_sequence') * 7919 + 104729) % 2176782336;
  generated := '';
  FOR digit IN 1..6 LOOP
   generated := substr(alphabet, (value % 36)::INTEGER + 1, 1) || generated;
   value := value / 36;
  END LOOP;
  EXIT WHEN NOT EXISTS (SELECT 1 FROM clubs WHERE code = generated);
 END LOOP;
 RETURN generated;
END; $$;
UPDATE clubs SET code = generate_club_code() WHERE code IS NULL;
ALTER TABLE clubs ALTER COLUMN code SET DEFAULT generate_club_code();
ALTER TABLE clubs ALTER COLUMN code SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_clubs_code ON clubs(code);
ALTER TABLE club_members DROP CONSTRAINT IF EXISTS ck_club_members_club_member_status;
ALTER TABLE club_members ADD CONSTRAINT ck_club_members_club_member_status CHECK (status IN ('pending','accepted','declined','requested'));
COMMIT;
