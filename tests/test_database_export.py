"""Verifica que a recriação inclui o esquema atual em uma única transação."""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.export_database_schema import export_schema
from src.models import Base


class DatabaseExportTests(unittest.TestCase):
    def generated_sql(self):
        with patch.object(Path, 'write_text') as write, patch('builtins.print'):
            export_schema()
        write.assert_called_once()
        return write.call_args.args[0]

    def test_contains_every_current_model_and_no_seed_data(self):
        sql = self.generated_sql()
        tables = set(re.findall(r'^CREATE TABLE ([a-z_]+) \(', sql, re.MULTILINE))
        self.assertEqual(tables, set(Base.metadata.tables))
        self.assertNotRegex(sql, r'(?im)^\s*INSERT\s+INTO\b')
        for table in ('club_members', 'event_team_players'):
            definition = re.search(rf'^CREATE TABLE {table} \((.*?)^\);', sql, re.MULTILINE | re.DOTALL).group(1)
            self.assertIn('jersey_number INTEGER', definition)
            self.assertIn('jersey_number BETWEEN 0 AND 100', definition)

    def test_migration_transactions_do_not_commit_partial_bootstrap(self):
        sql = self.generated_sql()
        boundaries = re.findall(r'^(BEGIN|COMMIT);\s*$', sql, re.MULTILINE)
        self.assertEqual(boundaries, ['BEGIN', 'COMMIT'])
        self.assertTrue(sql.rstrip().endswith('COMMIT;'))
        self.assertIn('-- Complemento: migrations/028_jersey_numbers.sql', sql)

    def test_saved_bootstrap_matches_current_models_and_migrations(self):
        saved = Path('src/databases/scripts/create_database.sql').read_text(encoding='utf-8-sig')
        generated = self.generated_sql()
        # SQLAlchemy guarda índices em sets: a ordem pode variar entre processos.
        indexes = re.compile(r'^CREATE (?:UNIQUE )?INDEX .+;\n', re.MULTILINE)
        self.assertEqual(sorted(indexes.findall(saved)), sorted(indexes.findall(generated)))
        self.assertEqual(indexes.sub('', saved), indexes.sub('', generated))
