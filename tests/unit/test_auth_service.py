import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.exceptions import ConflictException, UnauthorizedException
from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.auth.service import AuthService


@pytest.mark.asyncio
async def test_register_success(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    user_repo.get_by_email = AsyncMock(return_value=None)
    fake_user = MagicMock(
        id=uuid.uuid4(), email="new@reliastra.com", password_hash="hash", is_active=True
    )
    user_repo.create = AsyncMock(return_value=fake_user)

    fake_org = MagicMock(id=uuid.uuid4(), name="My Org", slug="my-org")
    org_repo.get_by_slug = AsyncMock(return_value=None)
    org_repo.create = AsyncMock(return_value=fake_org)
    org_repo.add_member = AsyncMock()
    mocker.patch(
        "app.modules.agencies.repository.AgencyRepository.create_application",
        new=AsyncMock(),
    )

    auth_repo.create_refresh_token = AsyncMock()

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )

    req = RegisterRequest(
        email="new@reliastra.com", password="Password123!", full_name="New User"
    )
    session = AsyncMock()
    result = await service.register(session, req)

    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.token_type == "bearer"
    user_repo.create.assert_called_once()
    org_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_register_conflict(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    user_repo.get_by_email = AsyncMock(
        return_value=MagicMock(id=uuid.uuid4())
    )

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )

    req = RegisterRequest(
        email="existing@reliastra.com",
        password="Password123!",
        full_name="New User",
    )
    session = AsyncMock()

    with pytest.raises(ConflictException):
        await service.register(session, req)


@pytest.mark.asyncio
async def test_login_success(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    from app.core.security import get_password_hash
    pwd_hash = get_password_hash("Password123!")

    fake_user = MagicMock(
        id=uuid.uuid4(), email="user@reliastra.com", password_hash=pwd_hash, is_active=True
    )
    user_repo.get_by_email = AsyncMock(return_value=fake_user)
    auth_repo.create_refresh_token = AsyncMock()

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )

    req = LoginRequest(email="user@reliastra.com", password="Password123!")
    session = AsyncMock()
    result = await service.login(session, req)

    assert result.access_token is not None
    assert result.refresh_token is not None


@pytest.mark.asyncio
async def test_login_invalid_password(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    from app.core.security import get_password_hash
    pwd_hash = get_password_hash("CorrectPassword!")

    fake_user = MagicMock(
        id=uuid.uuid4(), email="user@reliastra.com", password_hash=pwd_hash, is_active=True
    )
    user_repo.get_by_email = AsyncMock(return_value=fake_user)

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )

    req = LoginRequest(email="user@reliastra.com", password="WrongPassword!")
    session = AsyncMock()

    with pytest.raises(UnauthorizedException):
        await service.login(session, req)


@pytest.mark.asyncio
async def test_refresh_success(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    from app.core.security import create_refresh_token
    user_id = uuid.uuid4()
    rt_str = create_refresh_token(str(user_id))

    family = uuid.uuid4()
    auth_repo.get_refresh_token = AsyncMock(
        return_value=MagicMock(
            is_revoked=False, token_family=family, token_sequence=1
        )
    )
    auth_repo.get_latest_sequence = AsyncMock(return_value=1)
    auth_repo.create_refresh_token = AsyncMock()
    auth_repo.revoke_refresh_token = AsyncMock()
    user_repo.get_by_id = AsyncMock(return_value=MagicMock(id=user_id, is_active=True))

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )
    session = AsyncMock()
    result = await service.refresh(session, rt_str)

    assert result.access_token is not None
    # FIX 28: the rotated token belongs to the same family with sequence + 1.
    args, kwargs = auth_repo.create_refresh_token.call_args
    assert kwargs["token_family"] == family
    assert kwargs["token_sequence"] == 2


@pytest.mark.asyncio
async def test_refresh_rejects_replayed_sequence(mocker):
    auth_repo = MagicMock()
    user_repo = MagicMock()
    org_repo = MagicMock()

    from app.core.security import create_refresh_token
    user_id = uuid.uuid4()
    rt_str = create_refresh_token(str(user_id))

    family = uuid.uuid4()
    auth_repo.get_refresh_token = AsyncMock(
        return_value=MagicMock(
            is_revoked=False, token_family=family, token_sequence=1
        )
    )
    # The family has already advanced to sequence 2 → replay of sequence 1.
    auth_repo.get_latest_sequence = AsyncMock(return_value=2)
    auth_repo.revoke_family = AsyncMock()
    user_repo.get_by_id = AsyncMock(return_value=MagicMock(id=user_id, is_active=True))

    service = AuthService(
        auth_repository=auth_repo,
        user_repository=user_repo,
        org_repository=org_repo,
    )
    session = AsyncMock()

    with pytest.raises(UnauthorizedException):
        await service.refresh(session, rt_str)
    auth_repo.revoke_family.assert_awaited_once_with(session, family)


@pytest.mark.asyncio
async def test_logout_success(mocker):
    auth_repo = MagicMock()
    auth_repo.revoke_refresh_token = AsyncMock(return_value=True)

    service = AuthService(auth_repository=auth_repo)
    session = AsyncMock()
    await service.logout(session, "fake_token")

    auth_repo.revoke_refresh_token.assert_called_once_with(session, "fake_token")
