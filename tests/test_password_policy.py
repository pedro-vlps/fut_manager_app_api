import unittest
from uuid import uuid4
from pydantic import ValidationError
from src.helpers.password_policy import missing_password_requirements
from src.schemas.profiles import ProfileCreateSchema, ProfileUpdateSchema
from src.schemas.auth import LoginRequest
from tests.test_auth import AuthTestCase


class PasswordPolicyTests(unittest.TestCase):
    def test_each_requirement_and_unicode_boundaries(self):
        invalid = ('Ab1!', 'abcdef1!', 'ABCDEF1!', 'Abcdefg!', 'Abcdef12',
                   'Abcdef1 ', 'Abcdef1\n', 'Abcdef1\u200b', 'Aa1!' + 'a'*125)
        for password in invalid:
            with self.subTest(password=password):
                self.assertTrue(missing_password_requirements(password))
                for schema, fields in ((ProfileCreateSchema, {'name': 'Jogador', 'email': 'a@example.test', 'positions': {'campo': ['meia']}}),
                                       (ProfileUpdateSchema, {})):
                    with self.assertRaises(ValidationError):
                        schema(password=password, **fields)
        for password in ('Abcdef1!', 'Ábcdef1!', 'Ábcdef1🔒', 'Aa1!' + 'a'*124):
            with self.subTest(password=password):
                self.assertEqual(missing_password_requirements(password), [])
                self.assertEqual(ProfileUpdateSchema(password=password).password, password)

    def test_update_without_password_and_legacy_login(self):
        self.assertNotIn('password', ProfileUpdateSchema(name='Novo nome').model_dump(exclude_unset=True))
        with self.assertRaises(ValidationError):
            ProfileUpdateSchema(password=None)
        self.assertEqual(LoginRequest(email='a@example.test', password='legacy-password').password, 'legacy-password')


class PasswordRegistrationTests(AuthTestCase):
    async def test_register_rejects_missing_criteria_and_accepts_valid_password(self):
        payload = {'name': 'Jogador', 'email': f'{uuid4()}@example.test', 'positions': {'campo': ['meia']}}
        for password in ('Ab1!', 'abcdef1!', 'ABCDEF1!', 'Abcdefg!', 'Abcdef12', 'Abcdef1 '):
            response = await self.client.post('/auth/register', json={**payload, 'password': password})
            self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.post('/auth/register', json={**payload, 'password': 'Abcdef1!'})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn('password', response.json())
        response = await self.client.post('/auth/login', json={'email': payload['email'], 'password': 'Abcdef1!'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.login()).status_code, 200)  # Conta antiga continua entrando.
