"""Create the requested PSF test roster atomically; reruns never reset passwords."""
import argparse
import asyncio
import json
import os
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from src.configs.db_connection import SessionLocal, engine
from src.models.entities import Profile, PeladaGroup, GroupMember, PeladaEvent, EventPresence
from src.models.enums import GroupRole, MembershipStatus, EventStatus, PresenceStatus, TeamPlayerRole

ROSTER = [
    ('Yago', 'yago'), ('WL', 'wl'), ('JP', 'jp'), ('Pedro Vieira', 'pedro.vieira'),
    ('Japa', 'japa'), ('Gg', 'gg'), ('JV', 'jv'), ('Maderson', 'maderson'),
    ('Marcondes', 'marcondes'), ('Trompete', 'trompete'), ('Daniel Camargo', 'daniel.camargo'),
    ('Xavier', 'xavier'), ('Lino', 'lino'), ('Hugo', 'hugo'), ('Gustavo', 'gustavo'),
    ('Caleb', 'caleb'), ('Guilherme', 'guilherme'), ('Lucas', 'lucas'),
    ('Marlon', 'marlon'), ('Sandro', 'sandro'),
]


def uid(key):
    return uuid5(NAMESPACE_URL, 'futmanager:psf:2026-09-26:' + key)


async def run(args):
    async with SessionLocal() as db, db.begin():
        owner = await db.scalar(select(Profile).where(func.lower(Profile.email) == 'email@email.com'))
        existing_groups = (await db.scalars(select(PeladaGroup).where(func.lower(PeladaGroup.name) == 'psf'))).all()
        profiles = (await db.scalars(select(Profile).where(
            (Profile.email.in_([slug + '@psf.test' for _, slug in ROSTER])) |
            (func.lower(Profile.name).in_([name.lower() for name, _ in ROSTER]))
        ))).all()
        if args.inspect:
            print(json.dumps({'owner': {'id': str(owner.id), 'name': owner.name, 'active': owner.is_active} if owner else None,
                'groups': [{'id': str(g.id), 'name': g.name} for g in existing_groups],
                'matching_profiles': [{'id': str(p.id), 'name': p.name, 'email': p.email} for p in profiles]}, ensure_ascii=False))
            return
        if owner is None or not owner.is_active:
            raise ValueError('A conta owner existente precisa estar ativa.')
        if any(g.id != uid('group') for g in existing_groups):
            raise ValueError('Já existe outro grupo PSF; nenhuma alteração foi feita.')
        password = os.environ['PSF_INITIAL_PASSWORD']

        async def ensure(model, key, **values):
            item = await db.get(model, uid(key))
            if item is None:
                item = model(id=uid(key), **values)
                db.add(item)
                await db.flush()
            return item

        group = await ensure(PeladaGroup, 'group', name='PSF', created_by_id=owner.id)
        await ensure(GroupMember, 'owner', group_id=group.id, profile_id=owner.id,
                     role=GroupRole.OWNER, status=MembershipStatus.ACTIVE)
        scheduled = datetime(2026, 9, 26, 22, tzinfo=ZoneInfo('America/Sao_Paulo'))
        event = await ensure(PeladaEvent, 'event', group_id=group.id, created_by_id=owner.id,
            title='PSF · 26/09 às 22h', scheduled_at=scheduled, modality=args.modality,
            registration_closes_at=scheduled, schedule_timezone='America/Sao_Paulo',
            min_confirmed_players=18, max_confirmed_players=18,
            min_confirmed_goalkeepers=2, max_confirmed_goalkeepers=2,
            status=EventStatus.REGISTRATION_OPEN)
        accounts = []
        for index, (name, slug) in enumerate(ROSTER):
            email = slug + '@psf.test'
            collision = await db.scalar(select(Profile).where(func.lower(Profile.email) == email))
            if collision and collision.id != uid('profile:' + slug):
                raise ValueError(f'O login {email} já está em uso; nenhuma alteração foi feita.')
            keeper = index >= 18
            profile = await ensure(Profile, 'profile:' + slug, name=name, email=email,
                password=password, is_active=True,
                positions={args.modality: ['goleiro']} if keeper and args.modality else {})
            await ensure(GroupMember, 'member:' + slug, group_id=group.id, profile_id=profile.id,
                role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE)
            await ensure(EventPresence, 'presence:' + slug, event_id=event.id, profile_id=profile.id,
                role=TeamPlayerRole.GOALKEEPER if keeper else TeamPlayerRole.PLAYER,
                status=PresenceStatus.CONFIRMED, confirmed_at=datetime.now(ZoneInfo('America/Sao_Paulo')))
            accounts.append({'name': name, 'email': email, 'role': 'goalkeeper' if keeper else 'player'})
        await db.flush()
        rows = (await db.scalars(select(EventPresence).where(EventPresence.event_id == event.id)
                               .execution_options(populate_existing=True))).all()
        assert len(rows) == 20 and all(p.status == PresenceStatus.CONFIRMED for p in rows)
        assert sum(p.role == TeamPlayerRole.GOALKEEPER for p in rows) == 2
        assert all(p.profile_id != owner.id for p in rows)
        print(json.dumps({'group_id': str(group.id), 'code': group.code, 'event_id': str(event.id),
            'scheduled_at': event.scheduled_at.isoformat(), 'modality': event.modality,
            'confirmed_players': 18, 'confirmed_goalkeepers': 2, 'owner_confirmed': False,
            'accounts': accounts}, ensure_ascii=False))
    await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--modality', choices=['campo', 'futsal', 'fut7'])
    asyncio.run(run(parser.parse_args()))
