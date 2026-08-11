import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.api_keys.service import ApiKeyService
from app.modules.api_keys.schemas import ApiKeyCreateRequest


@pytest.mark.asyncio
async def test_create_api_key():
    repo = MagicMock()
    org_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    fake_key = MagicMock()
    fake_key.id = uuid.uuid4()
    fake_key.org_id = org_id
    fake_key.name = "CI/CD Key"
    fake_key.prefix = "rel_1234"
    fake_key.scopes = ["read:checks"]
    fake_key.last_used_at = None
    fake_key.expires_at = None
    fake_key.created_at = now

    repo.create = AsyncMock(return_value=fake_key)

    service = ApiKeyService(repository=repo)
    session = AsyncMock()
    req = ApiKeyCreateRequest(name="CI/CD Key", scopes=["read:checks"])
    res = await service.create_key(session, org_id, req)

    assert res.full_key.startswith("rel_")
    assert res.name == "CI/CD Key"
