-- Pare as escritas, aplique este SQL, configure as chaves e execute encrypt_personal_data.py.
BEGIN;
DROP INDEX IF EXISTS profiles_email_lower_unique;
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_email_key;
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS uq_profiles_email;
ALTER TABLE profiles ALTER COLUMN name TYPE TEXT;
ALTER TABLE profiles ALTER COLUMN email TYPE TEXT;
ALTER TABLE profiles ALTER COLUMN avatar_url TYPE TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_lookup VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_profiles_email_lookup ON profiles(email_lookup);
ALTER TABLE group_guests ALTER COLUMN name TYPE TEXT;
ALTER TABLE championship_matches ALTER COLUMN actions DROP DEFAULT;
ALTER TABLE championship_matches ALTER COLUMN actions TYPE TEXT USING actions::text;
ALTER TABLE group_seasons ALTER COLUMN archived_rankings TYPE TEXT USING archived_rankings::text;
COMMIT;
