-- Perfis autenticáveis por e-mail e senha; telefones deixam de ser armazenados.
ALTER TABLE profiles DROP COLUMN IF EXISTS phone;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- Perfis legados não possuem senha em texto puro para migração segura.
-- Eles devem definir uma senha nova antes de conseguir fazer login.
UPDATE profiles
   SET password_hash = 'RESET_REQUIRED'
 WHERE password_hash IS NULL;

ALTER TABLE profiles
    ALTER COLUMN password_hash SET NOT NULL;
