from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)

# RFC 1918 / RFC 3927 / link-local / loopback ranges that must never be hit
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),         # unique local
    ipaddress.ip_network("fe80::/10"),         # link-local
]

# Loopback networks (permitted only when SSRF_ALLOW_LOOPBACK=true)
_LOOPBACK_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]

_ALLOWED_SCHEMES = {"http", "https"}


def _effective_blocked_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Build the blocked network list, honoring the SSRF tuning settings."""
    from app.config import settings

    blocked = [n for n in _BLOCKED_NETWORKS]
    if getattr(settings, "SSRF_ALLOW_LOOPBACK", False):
        blocked = [n for n in blocked if n not in _LOOPBACK_NETWORKS]

    allowed_cidrs = getattr(settings, "SSRF_ALLOWED_CIDRS", []) or []
    for cidr in allowed_cidrs:
        try:
            blocked = [n for n in blocked if not n.subnet_of(ipaddress.ip_network(cidr))]
        except ValueError as exc:
            logger.warning("Ignoring invalid SSRF_ALLOWED_CIDRS entry '%s': %s", cidr, exc)
    return blocked


def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to all its IP addresses."""
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return [r[4][0] for r in results]
    except socket.gaierror:
        return []


def is_url_safe(url: str, *, allowed_schemes: set[str] | None = None) -> tuple[bool, str]:
    """
    Validate that *url* does not point to a private / internal IP range.

    Returns (is_safe, reason).  When *is_safe* is False, *reason* explains why.
    """
    allowed = allowed_schemes or _ALLOWED_SCHEMES

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        return False, f"Cannot parse URL: {exc}"

    if parsed.scheme.lower() not in allowed:
        return False, f"Scheme '{parsed.scheme}' is not allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    blocked_networks = _effective_blocked_networks()

    # Check if the hostname itself is a numeric IP
    try:
        ip = ipaddress.ip_address(hostname)
        for net in blocked_networks:
            if ip in net:
                return False, f"IP {hostname} points to a private/blocked network"
    except ValueError:
        pass  # not a numeric IP, proceed with DNS resolution

    # Resolve the hostname and check every resolved IP
    resolved_ips = _resolve_hostname(hostname)
    if not resolved_ips:
        return False, f"Cannot resolve hostname '{hostname}'"

    for resolved in resolved_ips:
        try:
            ip = ipaddress.ip_address(resolved)
            for net in blocked_networks:
                if ip in net:
                    return (
                        False,
                        f"Hostname '{hostname}' resolves to {resolved}, "
                        f"which is in a private/blocked network",
                    )
        except ValueError:
            continue

    return True, ""


def validate_outbound_url(url: str, *, allowed_schemes: set[str] | None = None) -> None:
    """
    Raise ``ValueError`` when *url* targets a blocked IP range or uses
    a disallowed scheme.  Safe to call from service-layer code.
    """
    safe, reason = is_url_safe(url, allowed_schemes=allowed_schemes)
    if not safe:
        raise ValueError(f"URL safety check failed: {reason}")
