from uuid import uuid4
from tests.test_auth import AuthTestCase
from src.schemas.crud import ProfileCreateSchema, ProfileUpdateSchema
from pydantic import ValidationError


class ProfilePositionTests(AuthTestCase):
    async def test_view_and_edit_own_profile(self):
        token = (await self.login()).json()['access_token']
        headers = {'Authorization':f'Bearer {token}'}
        self.assertEqual((await self.client.get('/auth/me')).status_code, 401)
        self.assertEqual((await self.client.post('/auth/me/positions', json={'positions':{'campo':['meia']}})).status_code, 401)
        response = await self.client.get('/auth/me', headers=headers)
        self.assertEqual(response.json()['id'], str(self.user.id))
        self.assertNotIn('password', response.text)
        for positions in [{}, None, {'futsal':[]}, {'futsal':['zagueiro']}]:
            response = await self.client.post('/auth/me/positions', json={'positions':positions}, headers=headers)
            self.assertEqual(response.status_code, 422)
        positions = {'campo':['meia','volante'], 'fut7':['fixo']}
        response = await self.client.post('/auth/me/positions', json={'positions':positions, 'profile_id':str(self.other.id)}, headers=headers)
        self.assertEqual(response.status_code, 422)
        response = await self.client.post('/auth/me/positions', json={'positions':positions}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['positions'], positions)
        self.assertEqual((await self.client.get('/auth/me', headers=headers)).json()['positions'], positions)
        await self.db.refresh(self.other)
        self.assertEqual(self.other.positions, {})
        self.assertEqual((await self.login()).json()['profile']['positions'], positions)

    async def test_registration_positions_persist_and_login(self):
        positions = {'campo':['goleiro','volante'], 'futsal':['fixo','pivo'], 'fut7':['meia','ala_direita']}
        payload = {'name':'Jogador novo', 'email':f'{uuid4()}@example.test', 'password':'test-password-123', 'positions':positions}
        response = await self.client.post('/auth/register', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['positions'], positions)
        self.assertNotIn('password', response.text)
        response = await self.client.post('/auth/login', json={'email':payload['email'], 'password':payload['password']})
        self.assertEqual(response.json()['profile']['positions'], positions)
        response = await self.client.post('/auth/register', json=payload)
        self.assertEqual(response.status_code, 409)
        catalog = (await self.client.get('/auth/modalities')).json()
        self.assertEqual(set(catalog), {'campo','futsal','fut7'})

    async def test_invalid_positions_and_partial_updates(self):
        base = {'name':'Teste', 'email':f'{uuid4()}@example.test', 'password':'test-password-123'}
        for positions in [None, {}, {'futsal':[]}, {'basquete':['goleiro']}, {'futsal':['zagueiro']},
            {'campo':['goleiro','goleiro']}, {'campo':['goleiro'], 'futsal':[]}]:
            response = await self.client.post('/auth/register', json={**base,'positions':positions})
            self.assertEqual(response.status_code, 422, response.text)
            with self.assertRaises(ValidationError):
                ProfileUpdateSchema(positions=positions)
        self.assertEqual((await self.client.post('/auth/register', json=base)).status_code, 422)
        with self.assertRaises(ValidationError):
            ProfileCreateSchema(**base)
        self.assertNotIn('positions', ProfileUpdateSchema(name='Outro nome').model_dump(exclude_unset=True))

    async def test_generic_profile_crud_requires_positions(self):
        from api_crud_generate_libary.routers.router import Router
        from src.models import CRUD_MODELS
        options = CRUD_MODELS[0]
        self.app.include_router(Router(**{k:v for k,v in options.items() if k not in {'prefix','tags'}}).router, prefix='/profiles')
        payload = {'name':'CRUD teste', 'email':f'{uuid4()}@example.test', 'password':'test-password-123'}
        response = await self.client.post('/profiles', json=payload)
        self.assertEqual(response.status_code, 422)
        payload['positions'] = {'fut7':['fixo','pivo']}
        response = await self.client.post('/profiles', json=payload)
        self.assertIn(response.status_code, [200,201], response.text)
        response = await self.client.post('/auth/login', json={'email':payload['email'], 'password':payload['password']})
        profile = response.json()['profile']
        self.assertEqual(profile['positions'], payload['positions'])
        for positions in [None, {}, {'campo':['pivo']}]:
            response = await self.client.patch(f"/profiles/{profile['id']}", json={'positions':positions})
            self.assertEqual(response.status_code, 422, response.text)
