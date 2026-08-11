import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.core.permissions import Role
from app.modules.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationMemberInviteRequest,
    OrganizationMemberRoleUpdateRequest,
    OrganizationUpdateRequest,
)
from app.modules.organizations.service import OrganizationService


@pytest.mark.asyncio
async def test_list_my_orgs():
    org_repo = MagicMock()
    user_repo = MagicMock()
    now = datetime.now(timezone.utc)
    fake_org = MagicMock()
    fake_org.id = uuid.uuid4()
    fake_org.name = "Org 1"
    fake_org.slug = "org-1"
    fake_org.plan = "free"
    fake_org.stripe_customer_id = None
    fake_org.stripe_subscription_id = None
    fake_org.created_at = now
    fake_org.updated_at = now
    org_repo.list_for_user = AsyncMock(return_value=[fake_org])

    service = OrganizationService(org_repository=org_repo, user_repository=user_repo)
    session = AsyncMock()
    result = await service.list_my_orgs(session, uuid.uuid4())

    assert len(result) == 1
    assert result[0].name == "Org 1"


@pytest.mark.asyncio
async def test_create_org_success():
    org_repo = MagicMock()
    user_repo = MagicMock()
    now = datetime.now(timezone.utc)
    org_repo.get_by_slug = AsyncMock(return_value=None)
    fake_org = MagicMock()
    fake_org.id = uuid.uuid4()
    fake_org.name = "New Org"
    fake_org.slug = "new-org"
    fake_org.plan = "free"
    fake_org.stripe_customer_id = None
    fake_org.stripe_subscription_id = None
    fake_org.created_at = now
    fake_org.updated_at = now
    org_repo.create = AsyncMock(return_value=fake_org)
    org_repo.add_member = AsyncMock()

    service = OrganizationService(org_repository=org_repo, user_repository=user_repo)
    session = AsyncMock()
    req = OrganizationCreateRequest(name="New Org", slug="new-org")
    result = await service.create_org(session, uuid.uuid4(), req)

    assert result.name == "New Org"
    assert result.slug == "new-org"


@pytest.mark.asyncio
async def test_invite_member_success():
    org_repo = MagicMock()
    user_repo = MagicMock()
    now = datetime.now(timezone.utc)
    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    fake_user.email = "member@reliastra.com"
    user_repo.get_by_email = AsyncMock(return_value=fake_user)
    org_repo.get_member = AsyncMock(return_value=None)

    fake_member = MagicMock()
    fake_member.id = uuid.uuid4()
    fake_member.org_id = uuid.uuid4()
    fake_member.user_id = fake_user.id
    fake_member.role = Role.MEMBER.value
    fake_member.joined_at = now
    org_repo.add_member = AsyncMock(return_value=fake_member)

    service = OrganizationService(org_repository=org_repo, user_repository=user_repo)
    session = AsyncMock()
    req = OrganizationMemberInviteRequest(email="member@reliastra.com", role=Role.MEMBER)
    result = await service.invite_member(session, fake_member.org_id, req)

    assert result.user_id == fake_user.id
    assert result.role == Role.MEMBER.value
