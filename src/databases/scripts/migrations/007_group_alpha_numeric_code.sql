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
