"""Tests for FIX 26: DNS-rebinding-safe SSRF protection with IP pinning."""

import ipaddress
from unittest.mock import patch

import pytest

from app.core.ssrf_protection import (
    PinnedTarget,
    pinned_transport_for,
    resolve_pinned_target,
    validate_outbound_url,
)


def test_validate_blocks_private_ip_literal():
    with pytest.raises(ValueError):
        validate_outbound_url("http://127.0.0.1:8080/admin")
    with pytest.raises(ValueError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(ValueError):
        validate_outbound_url("http://10.0.0.5/secret")


def test_validate_blocks_hostname_resolving_to_private_ip():
    with patch(
        "app.core.ssrf_protection._resolve_hostname",
        return_value=["192.168.1.10"],
    ):
        with pytest.raises(ValueError):
            validate_outbound_url("https://evil.example.com/steal")


def test_resolve_pinned_target_returns_public_ips():
    with patch(
        "app.core.ssrf_protection._resolve_hostname",
        return_value=["93.184.216.34"],
    ):
        target = resolve_pinned_target("https://example.com/health")
    assert target.hostname == "example.com"
    assert target.port == 443
    assert target.ips == ["93.184.216.34"]
    for ip in target.ips:
        assert ipaddress.ip_address(ip).is_private is False


def test_resolve_pinned_target_raises_when_any_ip_is_private():
    # DNS rebinding protection: even ONE private IP in the answer set blocks.
    with patch(
        "app.core.ssrf_protection._resolve_hostname",
        return_value=["93.184.216.34", "169.254.169.254"],
    ):
        with pytest.raises(ValueError):
            resolve_pinned_target("https://evil.example.com/")


def test_pinned_transport_uses_pinned_ip_and_keeps_sni_hostname():
    target = PinnedTarget(
        url="https://example.com/x",
        hostname="example.com",
        port=443,
        ips=["93.184.216.34"],
    )
    transport = pinned_transport_for(target)
    # The pool's origin must be the pinned IP, NOT the hostname.
    assert transport._origin.host == b"93.184.216.34"
    assert transport._hostname == "example.com"


def test_pinned_transport_cache_is_reused():
    target = PinnedTarget(
        url="https://example.com/x",
        hostname="example.com",
        port=443,
        ips=["93.184.216.34"],
    )
    first = pinned_transport_for(target)
    second = pinned_transport_for(target)
    assert first is second
