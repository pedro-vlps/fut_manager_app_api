from datetime import datetime, timezone
from fastapi import HTTPException
from src.models.entities import GroupJoinRequest, GroupMember, Profile
from src.models.enums import GroupRole, MembershipStatus
from src.schemas.group_requests import DiscoveredGroup, JoinRequestSchema, JoinRequestPerson
from src.services.group_requests import GroupRequestsService


async def require_manager(service, group, profile):
    member = await service.membership(group.id, profile.id)
    if group.created_by_id != profile.id and not (
        member and member.status == MembershipStatus.ACTIVE
        and member.role in {GroupRole.OWNER, GroupRole.ADMIN}
    ):
        raise HTTPException(403, "Somente owners e administradores podem gerenciar pedidos.")


async def search(query, profile, db):
    service = GroupRequestsService(db)
    group = await service.by_code(query.code.upper())
    if group is None:
        raise HTTPException(404, "Nenhum grupo encontrado com este código.")
    member = await service.membership(group.id, profile.id)
    existing = await service.existing_request(group.id, profile.id)
    state = "none"
    if group.created_by_id == profile.id or (member and member.status == MembershipStatus.ACTIVE):
        state = "active"
    elif member and member.status == MembershipStatus.BLOCKED:
        state = "blocked"
    return DiscoveredGroup(id=group.id, name=group.name, code=group.code,
                           description=group.description, membership=state,
                           request_status=existing.status if existing else None)


async def request_join(group_id, profile, db):
    service = GroupRequestsService(db)
    group = await service.locked_group(group_id)
    if group is None:
        raise HTTPException(404, "Grupo não encontrado.")
    member = await service.membership(group.id, profile.id)
    if group.created_by_id == profile.id or (member and member.status == MembershipStatus.ACTIVE):
        raise HTTPException(409, "Você já faz parte deste grupo.")
    if member and member.status == MembershipStatus.BLOCKED:
        raise HTTPException(403, "Sua entrada neste grupo está bloqueada.")
    item = await service.existing_request(group.id, profile.id)
    if item is None:
        item = GroupJoinRequest(group_id=group.id, profile_id=profile.id)
        service.add(item)
    else:
        item.status = "pending"
        item.reviewed_at = None
        item.reviewed_by_id = None
    await service.flush()
    result = JoinRequestSchema.model_validate(item)
    await service.commit()
    return result


async def list_requests(group, profile, db):
    service = GroupRequestsService(db)
    await require_manager(service, group, profile)
    return [JoinRequestPerson(**JoinRequestSchema.model_validate(item).model_dump(), name=name)
            for item, name in await service.pending_requests(group.id)]


async def review(group, request_id, payload, profile, db):
    service = GroupRequestsService(db)
    group = await service.locked_group(group.id)
    await require_manager(service, group, profile)
    item = await service.get(GroupJoinRequest, request_id)
    if item is None or item.group_id != group.id:
        raise HTTPException(404, "Pedido não encontrado neste grupo.")
    if item.status != "pending":
        raise HTTPException(409, "Este pedido já foi analisado.")
    if payload.decision == "approve":
        applicant = await service.get(Profile, item.profile_id)
        if applicant is None or not applicant.is_active:
            raise HTTPException(409, "Este usuário está inativo.")
        member = await service.membership(group.id, item.profile_id)
        if member and member.status == MembershipStatus.BLOCKED:
            raise HTTPException(409, "Este usuário está bloqueado no grupo.")
        if member is None:
            member = GroupMember(group_id=group.id, profile_id=item.profile_id, role=GroupRole.MEMBER)
            service.add(member)
        elif member.status != MembershipStatus.ACTIVE:
            member.role = GroupRole.MEMBER
        member.status = MembershipStatus.ACTIVE
    item.status = "approved" if payload.decision == "approve" else "rejected"
    item.reviewed_by_id = profile.id
    item.reviewed_at = datetime.now(timezone.utc)
    await service.flush()
    result = JoinRequestSchema.model_validate(item)
    await service.commit()
    return result
