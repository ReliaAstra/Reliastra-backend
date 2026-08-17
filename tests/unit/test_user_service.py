import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.modules.users.schemas import UserUpdateRequest
from app.modules.users.service import UserService


@pytest.mark.asyncio
async def test_get_profile_success():
    repo = MagicMock()
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    fake_user = MagicMock(
        id=user_id,
        email="test@reliastra.com",
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        avatar_url=None,
        auth_provider=None,
        created_at=now,
        updated_at=now,
    )
    repo.get_by_id = AsyncMock(return_value=fake_user)

    service = UserService(repository=repo)
    session = AsyncMock()
    result = await service.get_profile(session, user_id)

    assert result.id == user_id
    assert result.email == "test@reliastra.com"


@pytest.mark.asyncio
async def test_get_profile_not_found():
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)

    service = UserService(repository=repo)
    session = AsyncMock()

    with pytest.raises(ResourceNotFoundException):
        await service.get_profile(session, uuid.uuid4())


@pytest.mark.asyncio
async def test_update_profile_success():
    repo = MagicMock()
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    fake_user = MagicMock(
        id=user_id,
        email="test@reliastra.com",
        full_name="Old Name",
        is_active=True,
        is_superuser=False,
        avatar_url=None,
        auth_provider=None,
        created_at=now,
        updated_at=now,
    )
    repo.get_by_id = AsyncMock(return_value=fake_user)
    repo.get_by_email = AsyncMock(return_value=None)
    updated_user = MagicMock(
        id=user_id,
        email="newemail@reliastra.com",
        full_name="New Name",
        is_active=True,
        avatar_url=None,
        auth_provider=None,
        is_superuser=False,
        created_at=now,
        updated_at=now,
    )
    repo.update = AsyncMock(return_value=updated_user)

    service = UserService(repository=repo)
    session = AsyncMock()
    req = UserUpdateRequest(full_name="New Name", email="newemail@reliastra.com")
    result = await service.update_profile(session, user_id, req)

    assert result.full_name == "New Name"
    assert result.email == "newemail@reliastra.com"
