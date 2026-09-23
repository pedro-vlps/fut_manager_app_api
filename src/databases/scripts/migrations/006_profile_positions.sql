-- Perfis antigos ficam sem posições informadas, sem inventar preferências.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS positions JSONB NOT NULL DEFAULT '{}'::jsonb;
