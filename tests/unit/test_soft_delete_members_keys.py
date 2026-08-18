"""Soft-delete for organization members and API keys."""

import uuid

import pytest

from app.core.exceptions import UnauthorizedException
from app.core.security import generate_api_key
from app.modules.api_keys.models import ApiKey
from app.modules.api_keys.repository import ApiKeyRepository
from app.modules.api_keys.service import ApiKeyService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository


async def _org_and_user(db_session):
    user = await UserRepository.create(
        db_session,
        email=f"owner-{uuid.uuid4().hex[:8]}@reliastra.com",
        password_hash="hashed",
        full_name="Owner",
    )
    org = await OrganizationRepository.create(
        db_session,
        name="Soft Delete Org",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        plan="free",
    )
    member = await OrganizationRepository.add_member(
        db_session, org.id, user.id, role="owner"
    )
    await db_session.commit()
    return org, user, member


@pytest.mark.asyncio
async def test_removed_member_is_soft_deleted_and_restorable(db_session):
    org, user, member = await _org_and_user(db_session)
    invitee = await UserRepository.create(
        db_session,
        email=f"invitee-{uuid.uuid4().hex[:8]}@reliastra.com",
        password_hash="hashed",
        full_name="Invitee",
    )
    invitee_member = await OrganizationRepository.add_member(
        db_session, org.id, invitee.id, role="member"
    )
    await db_session.commit()

    await OrganizationRepository.remove_member(db_session, invitee_member)
    await db_session.commit()

    active = await OrganizationRepository.list_members(db_session, org.id)
    assert [m.id for m in active] == [member.id]
    assert await OrganizationRepository.get_member(
        db_session, org.id, invitee.id
    ) is None

    deleted = await OrganizationRepository.get_member(
        db_session, org.id, invitee.id, include_deleted=True
    )
    assert deleted is not None
    assert deleted.is_deleted is True

    restored = await OrganizationRepository.restore_member(
        db_session, deleted, "admin"
    )
    await db_session.commit()
    assert restored.is_deleted is False
    assert restored.role == "admin"


@pytest.mark.asyncio
async def test_revoked_api_key_is_soft_deleted_and_cannot_auth(db_session):
    org, _user, _member = await _org_and_user(db_session)
    full_key, prefix, hashed_key = generate_api_key()
    key = ApiKey(
        org_id=org.id,
        name="ci-key",
        prefix=prefix,
        hashed_key=hashed_key,
        scopes=["read:checks"],
    )
    db_session.add(key)
    await db_session.commit()

    service = ApiKeyService()
    authenticated = await service.authenticate_key(db_session, full_key)
    assert authenticated.id == key.id

    await ApiKeyRepository.delete(db_session, key)
    await db_session.commit()

    listed = await ApiKeyRepository.list_for_org(db_session, org.id)
    assert listed == []

    with pytest.raises(UnauthorizedException):
        await service.authenticate_key(db_session, full_key)
