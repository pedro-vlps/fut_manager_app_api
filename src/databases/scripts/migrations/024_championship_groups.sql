BEGIN;
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_championship_capacity;
ALTER TABLE championships ADD CONSTRAINT ck_championships_championship_capacity
    CHECK (capacity IN (4, 8, 12, 16));
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_twelve_teams_groups;
ALTER TABLE championships ADD CONSTRAINT ck_championships_twelve_teams_groups
    CHECK (capacity <> 12 OR format = 'groups_knockout');
ALTER TABLE championship_entries ADD COLUMN IF NOT EXISTS pool VARCHAR(1);
COMMIT;
