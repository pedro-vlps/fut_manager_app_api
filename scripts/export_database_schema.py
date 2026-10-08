"""Exporta o bootstrap PostgreSQL sem conexão nem dados do banco existente.

Execute com as dependências/configurações da API: python -m scripts.export_database_schema
"""
import ast
from pathlib import Path
import src

from sqlalchemy import create_mock_engine
from src.models import Base


def export_schema():
    root = Path(next(iter(src.__path__))).resolve().parent
    scripts = root / 'src/databases/scripts'
    statements = []

    def emit(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=engine.dialect)).strip() + ';')

    engine = create_mock_engine('postgresql://', emit)
    Base.metadata.create_all(engine, checkfirst=False)
    # Reproduz os complementos SQL usados no bootstrap atual da aplicação.
    tree = ast.parse((scripts / 'create_schema.py').read_text(encoding='utf-8-sig'))
    migrations = sorted({node.value for node in ast.walk(tree)
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)
                         and node.value.startswith('migrations/') and node.value.endswith('.sql')})
    header = '''-- FutManager: esquema completo para um banco NOVO PostgreSQL 17.
-- Gerado pelos modelos atuais e pelo bootstrap da API. Sem usuários ou dados de teste.
-- 1. No servidor PostgreSQL, crie o banco (fora de uma transação):
--    CREATE DATABASE fut_manager WITH ENCODING 'UTF8';
-- 2. Conecte-se ao banco criado e execute este arquivo integralmente.
--    psql -h HOST -U USUARIO -d fut_manager -v ON_ERROR_STOP=1 -f create_database.sql
-- Em serviços gerenciados, use o banco vazio fornecido pelo provedor.
-- Este arquivo NÃO é uma migração para bancos existentes e não deve ser reaplicado.
-- Não contém DROP DATABASE, DROP TABLE nem credenciais.
-- IDs UUID e updated_at são preenchidos/atualizados pela API via SQLAlchemy.

BEGIN;
SET LOCAL search_path TO public;
'''
    parts = [header, '\n\n'.join(statements)]
    for migration in migrations:
        parts.append(f'\n-- Complemento: {migration}\n' + (scripts / migration).read_text(encoding='utf-8-sig'))
    parts.append('\nCOMMIT;\n')
    destination = scripts / 'create_database.sql'
    destination.write_text('\n\n'.join(parts), encoding='utf-8')
    print(f'{destination}: {len(Base.metadata.tables)} tabelas; {len(migrations)} complementos SQL.')


if __name__ == '__main__':
    export_schema()
