"""Tests for FIX 27 (hashed refresh tokens) and FIX 28 (family/replay detection)."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.modules.auth.repository import AuthRepository


async def _make_user(db_session):
    from app.modules.users.repository import UserRepository
    from app.core.security import get_password_hash

    user = await UserRepository.create(
        db_session,
        email=f"family-{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Family User",
    )
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_refresh_tokens_are_stored_hashed(db_session):
    """FIX 27: the DB row must contain a SHA-256 hash, never the token."""
    user = await _make_user(db_session)
    raw_token = "refresh-token-plaintext-abc123"
    rt = await AuthRepository.create_refresh_token(
        db_session, user.id, raw_token, datetime.now(timezone.utc)
    )
    assert rt.token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    assert rt.token_hash != raw_token


@pytest.mark.asyncio
async def test_refresh_token_family_sequence_rotation(db_session):
    user = await _make_user(db_session)
    user_id = user.id
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    first = await AuthRepository.create_refresh_token(
        db_session, user_id, "token-v1", expires
    )
    second = await AuthRepository.create_refresh_token(
        db_session,
        user_id,
        "token-v2",
        expires,
        token_family=first.token_family,
        token_sequence=2,
    )

    assert first.token_sequence == 1
    assert second.token_sequence == 2
    assert first.token_family == second.token_family

    latest = await AuthRepository.get_latest_sequence(
        db_session, first.token_family
    )
    assert latest == 2


@pytest.mark.asyncio
async def test_revoke_family_revokes_all_tokens(db_session):
    user = await _make_user(db_session)
    user_id = user.id
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    first = await AuthRepository.create_refresh_token(
        db_session, user_id, "family-token-1", expires
    )
    await AuthRepository.create_refresh_token(
        db_session,
        user_id,
        "family-token-2",
        expires,
        token_family=first.token_family,
        token_sequence=2,
    )

    revoked = await AuthRepository.revoke_family(db_session, first.token_family)
    assert revoked == 2

    token1 = await AuthRepository.get_refresh_token(db_session, "family-token-1")
    token2 = await AuthRepository.get_refresh_token(db_session, "family-token-2")
    assert token1.is_revoked is True
    assert token2.is_revoked is True


@pytest.mark.asyncio
async def test_refresh_service_rejects_replayed_token(db_session):
    """FIX 28 end-to-end: using an old (lower-sequence) token revokes the
    entire family."""
    from app.core.security import create_refresh_token
    from app.modules.auth.service import AuthService

    user = await _make_user(db_session)
    service = AuthService()

    # Two parallel valid tokens in one family: sequence 1 and sequence 2.
    raw_old = create_refresh_token(subject=str(user.id))
    raw_new = create_refresh_token(subject=str(user.id))
    first = await AuthRepository.create_refresh_token(
        db_session,
        user.id,
        raw_old,
        datetime.now(timezone.utc) + timedelta(days=7),
    )
    await AuthRepository.create_refresh_token(
        db_session,
        user.id,
        raw_new,
        datetime.now(timezone.utc) + timedelta(days=7),
        token_family=first.token_family,
        token_sequence=2,
    )
    await db_session.commit()

    # Presenting the OLD token (sequence 1 < latest 2) is reuse → revoke family.
    from app.core.exceptions import UnauthorizedException

    with pytest.raises(UnauthorizedException):
        await service.refresh(db_session, raw_old)
    await db_session.commit()

    # BOTH tokens in the family must now be revoked.
    old_row = await AuthRepository.get_refresh_token(db_session, raw_old)
    new_row = await AuthRepository.get_refresh_token(db_session, raw_new)
    assert old_row.is_revoked is True
    assert new_row.is_revoked is True
