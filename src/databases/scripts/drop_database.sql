-- FutManager: apaga TODOS os dados e objetos do esquema public do banco conectado.
-- Inclui contas, times, torneios, partidas, rankings, troféus, funções, enums e sequências.
-- Execute com a API parada e conectado ao banco da aplicação, usando seu proprietário.
-- O banco, seu nome e as credenciais do deploy são mantidos.
-- Qualquer outro objeto no esquema public também será apagado por CASCADE.
-- Depois execute create_database.sql inteiro na mesma conexão/banco.
-- psql -h HOST -U USUARIO -d NOME_DO_BANCO -v ON_ERROR_STOP=1 -f drop_database.sql

BEGIN;
SET LOCAL lock_timeout = '15s';

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public AUTHORIZATION CURRENT_USER;
GRANT USAGE ON SCHEMA public TO PUBLIC;

COMMIT;
