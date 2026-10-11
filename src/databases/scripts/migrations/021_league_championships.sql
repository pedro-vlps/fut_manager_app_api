BEGIN;
ALTER TABLE championships DROP CONSTRAINT IF EXISTS ck_championships_championship_format;
ALTER TABLE championships ADD CONSTRAINT ck_championships_championship_format
    CHECK (format IN ('groups_knockout', 'knockout', 'cascade', 'league'));
COMMIT;
