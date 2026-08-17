"""Tests for FIX 15 (dangerous header rejection), FIX 16 (region validation),
FIX 23 (no decrypted headers in API responses)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyUpdateRequest,
)


@pytest.mark.parametrize(
    "header_name",
    [
        "Host",
        "host",
        "Content-Length",
        "Transfer-Encoding",
        "Connection",
        "Proxy-Authorization",
        "proxy-whatever",
        "X-Forwarded-For",
        "x-forwarded-host",
    ],
)
def test_dangerous_headers_rejected_on_create(header_name):
    with pytest.raises(ValidationError):
        DependencyCreateRequest(
            name="dep",
            endpoint_url="https://example.com",
            headers={header_name: "evil"},
        )


@pytest.mark.parametrize(
    "header_name",
    ["Host", "Content-Length", "Transfer-Encoding", "Connection", "Proxy-X", "X-Forwarded-For"],
)
def test_dangerous_headers_rejected_on_update(header_name):
    with pytest.raises(ValidationError):
        DependencyUpdateRequest(headers={header_name: "evil"})


def test_safe_headers_allowed():
    request = DependencyCreateRequest(
        name="dep",
        endpoint_url="https://example.com",
        headers={"Authorization": "Bearer tok", "X-Custom-Thing": "1"},
    )
    assert request.headers["Authorization"] == "Bearer tok"


def test_unknown_region_rejected():
    with pytest.raises(ValidationError):
        DependencyCreateRequest(
            name="dep",
            endpoint_url="https://example.com",
            regions=["us-east", "mars-west-1"],
        )


def test_duplicate_regions_deduplicated():
    request = DependencyCreateRequest(
        name="dep",
        endpoint_url="https://example.com",
        regions=["us-east", "eu-west", "us-east", "ap-south"],
    )
    assert request.regions == ["us-east", "eu-west", "ap-south"]


def test_empty_regions_rejected():
    with pytest.raises(ValidationError):
        DependencyCreateRequest(
            name="dep", endpoint_url="https://example.com", regions=[]
        )


@pytest.mark.asyncio
async def test_response_masks_encrypted_headers():
    """FIX 23: DependencyResponse never exposes decrypted headers."""
    from datetime import datetime, timezone

    from app.modules.dependencies.models import Dependency
    from app.modules.dependencies.service import DependencyService

    now = datetime.now(timezone.utc)
    dep = Dependency(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        application_id=None,
        name="secret-dep",
        endpoint_url="https://example.com",
        method="GET",
        headers={
            "_encrypted_data": "gAAAAA-fake-fernet-token-for-authorization-bearer"
        },
        expected_status_codes=[200],
        timeout_seconds=10,
        check_interval_seconds=300,
        next_check_at=now,
        regions=["us-east"],
        alert_threshold_ms=None,
        is_active=True,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )

    response = DependencyService()._to_response(dep)
    assert response.has_headers is True
    assert response.headers is None
    # The plaintext secret must not appear anywhere in the serialized output.
    dumped = response.model_dump_json()
    assert "gAAAAA" not in dumped
