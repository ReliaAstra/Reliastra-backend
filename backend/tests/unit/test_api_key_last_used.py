"""Tests for FIX 11 (bcrypt auth lookup) and FIX 21 (Redis-backed last_used_at)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.core.security import generate_api_key, hash_api_key
from app.modules.api_keys.models import ApiKey
from app.modules.api_keys.repository import ApiKeyRepository
from app.modules.api_keys.service import ApiKeyService


async def _make_org(db_session):
    """Create a real organization row (api_keys.org_id has a FK)."""
    import uuid as _uuid

    from app.modules.organizations.repository import OrganizationRepository

    org = await OrganizationRepository.create(
        db_session,
        name="Key Org",
        slug=f"org-{_uuid.uuid4().hex[:8]}",
        plan="free",
    )
    await db_session.commit()
    return org


@pytest.mark.asyncio
async def test_authenticate_key_uses_prefix_and_bcrypt(db_session, fake_redis):
    """New (bcrypt) keys are located by prefix and verified with checkpw."""
    org = await _make_org(db_session)
    full_key, prefix, hashed_key = generate_api_key()
    key = ApiKey(
        org_id=org.id,
        name="ci-key",
        prefix=prefix,
        hashed_key=hashed_key,
        scopes=["read:checks"],
        expires_at=None,
    )
    db_session.add(key)
    await db_session.commit()

    service = ApiKeyService()
    authenticated = await service.authenticate_key(db_session, full_key)
    assert authenticated.id == key.id


@pytest.mark.asyncio
async def test_authenticate_key_rejects_wrong_key(db_session):
    from app.core.exceptions import UnauthorizedException

    org = await _make_org(db_session)
    full_key, prefix, hashed_key = generate_api_key()
    key = ApiKey(
        org_id=org.id,
        name="ci-key",
        prefix=prefix,
        hashed_key=hashed_key,
        scopes=["read:checks"],
        expires_at=None,
    )
    db_session.add(key)
    await db_session.commit()

    service = ApiKeyService()
    with pytest.raises(UnauthorizedException):
        await service.authenticate_key(db_session, "rel_" + "f" * 40)


@pytest.mark.asyncio
async def test_authenticate_key_writes_redis_not_db(db_session, fake_redis):
    """FIX 21: auth records last_used_at in Redis; no DB write happens."""
    org = await _make_org(db_session)
    full_key, prefix, hashed_key = generate_api_key()
    key = ApiKey(
        org_id=org.id,
        name="ci-key",
        prefix=prefix,
        hashed_key=hashed_key,
        scopes=["read:checks"],
        expires_at=None,
    )
    db_session.add(key)
    await db_session.commit()

    service = ApiKeyService(repository=MagicMock())
    service.repository.list_by_prefix = AsyncMock(return_value=[key])
    authenticated = await service.authenticate_key(db_session, full_key)
    assert authenticated.id == key.id

    # The last_used timestamp must be in Redis with a TTL…
    redis_value = await fake_redis.get(f"apikey:last_used:{key.id}")
    assert redis_value is not None
    ttl = await fake_redis.ttl(f"apikey:last_used:{key.id}")
    assert 0 < ttl <= 300

    # …and last_used_at in the DB row must be untouched.
    await db_session.refresh(key)
    assert key.last_used_at is None


@pytest.mark.asyncio
async def test_flush_api_key_last_used_batches_to_db(db_session, fake_redis):
    """FIX 21: the beat flush moves Redis timestamps into PostgreSQL."""
    org = await _make_org(db_session)
    full_key, prefix, hashed_key = generate_api_key()
    key = ApiKey(
        org_id=org.id,
        name="ci-key",
        prefix=prefix,
        hashed_key=hashed_key,
        scopes=["read:checks"],
        expires_at=None,
    )
    db_session.add(key)
    await db_session.commit()

    service = ApiKeyService()
    await service._record_last_used(key)
    assert await fake_redis.get(f"apikey:last_used:{key.id}") is not None

    from app.modules.api_keys.tasks import flush_api_key_last_used

    updated = flush_api_key_last_used()
    assert updated == 1

    await db_session.refresh(key)
    assert key.last_used_at is not None

    # Redis keys must be cleared after the flush.
    assert await fake_redis.get(f"apikey:last_used:{key.id}") is None


@pytest.mark.asyncio
async def test_update_last_used_batch_never_regresses(db_session):
    """A newer DB value must not be overwritten by an older Redis value."""
    org = await _make_org(db_session)
    key = ApiKey(
        org_id=org.id,
        name="batch-key",
        prefix="rel_test",
        hashed_key=hash_api_key("rel_test_not_used"),
        scopes=[],
        expires_at=None,
        last_used_at=datetime.now(timezone.utc),
    )
    db_session.add(key)
    await db_session.commit()
    newer = key.last_used_at

    older = newer - timedelta(minutes=10)
    count = await ApiKeyRepository.update_last_used_batch(
        db_session, {key.id: older}
    )
    await db_session.commit()
    assert count == 1

    await db_session.refresh(key)
    assert key.last_used_at == newer
