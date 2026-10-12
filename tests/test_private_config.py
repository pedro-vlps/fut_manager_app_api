import unittest
from scripts.check_private_config import inspect_file


class PrivateConfigTests(unittest.TestCase):
    def test_blank_example_is_allowed_without_consuming_next_line(self):
        self.assertEqual(inspect_file('.env.example',
            'FUT_MANAGER_DATABASE_HOST=\nFUT_MANAGER_DATABASE_USER=\nFUT_MANAGER_DATABASE_PASSWORD=\n'), [])

    def test_private_files_and_required_env_interpolation(self):
        self.assertTrue(inspect_file('.env', ''))
        self.assertTrue(inspect_file('private-config/config.json', '{}'))
        self.assertTrue(inspect_file('signing.key', ''))
        self.assertEqual(inspect_file('docker-compose.yml',
            'POSTGRES_PASSWORD: ${FUT_MANAGER_DATABASE_PASSWORD:?Obrigatória}'), [])

    def test_credentials_and_deployment_address_are_flagged_without_echoing_values(self):
        credential = 'synthetic' + '-private-value'
        findings = inspect_file('docker-compose.yml', 'POSTGRES_PASSWORD: ' + credential)
        self.assertTrue(findings)
        self.assertNotIn(credential, repr(findings))
        address = 'https://' + 'synthetic-app' + '.up.' + 'railway' + '.app'
        self.assertTrue(inspect_file('README.md', address))
        self.assertEqual(inspect_file('README.md', 'https://docs.expo.dev'), [])

    def test_native_infrastructure_ids_are_not_fixed(self):
        self.assertTrue(inspect_file('app.json', '{"projectId":"synthetic-project"}'))
        self.assertEqual(inspect_file('app.json', '{"name":"Fut Manager"}'), [])
