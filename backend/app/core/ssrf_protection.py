"""SSRF protection with DNS-rebinding-safe IP pinning.

The naive approach — resolve the hostname, validate the IPs, then let httpx
connect — has a TOCTOU window: an attacker-controlled DNS server can return a
public IP during validation and a private IP (e.g. 169.254.169.254) when the
HTTP client actually connects.

This module closes that window by **pinning the connection to a validated IP**:

1. ``resolve_pinned_target`` resolves the hostname once and verifies *every*
   resolved IP is public.
2. ``pinned_transport_for`` builds an httpcore-based transport whose TCP
   connection targets the pinned IP directly while TLS SNI, certificate
   hostname verification, and the ``Host`` header still use the original
   hostname (httpcore ``sni_hostname`` extension).

Transports are cached per (hostname, port, scheme, ip) so repeated checks
reuse warm httpcore connection pools.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
import urllib.parse
from typing import Any

import httpcore
import httpx

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

_ALLOWED_SCHEMES = {"http", "https"}


def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to all its IP addresses."""
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return [r[4][0] for r in results]
    except socket.gaierror:
        return []


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not any(ip in net for net in _BLOCKED_NETWORKS)


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

    # Check if the hostname itself is a numeric IP
    try:
        ip = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
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
            for net in _BLOCKED_NETWORKS:
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


# ---------------------------------------------------------------------------
# Pinned (DNS-rebinding-safe) transport
# ---------------------------------------------------------------------------

class PinnedTarget:
    """A validated URL together with the exact IPs the connection may use."""

    def __init__(self, url: str, hostname: str, port: int, ips: list[str]) -> None:
        self.url = url
        self.hostname = hostname
        self.port = port
        self.ips = ips


def resolve_pinned_target(url: str) -> PinnedTarget:
    """Validate *url* and pin it to its currently-resolved public IPs.

    Raises ``ValueError`` when the URL is unsafe or unresolvable.
    """
    validate_outbound_url(url)
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    resolved = _resolve_hostname(hostname)
    if not resolved:
        raise ValueError(f"Cannot resolve hostname '{hostname}'")
    for ip in resolved:
        if not _is_public_ip(ip):
            raise ValueError(
                f"Hostname '{hostname}' resolves to {ip}, "
                f"which is in a private/blocked network"
            )
    use_ssl = parsed.scheme.lower() == "https"
    port = parsed.port or (443 if use_ssl else 80)
    return PinnedTarget(url=url, hostname=hostname, port=port, ips=resolved)


class _PinnedIPTransport(httpx.AsyncBaseTransport):
    """httpx transport that connects to a fixed IP while preserving TLS/SNI.

    The connection pool's origin host is the pinned IP; the ``sni_hostname``
    extension tells httpcore to verify the server certificate against the real
    hostname and to send it during the TLS handshake.
    """

    def __init__(
        self,
        hostname: str,
        ip: str,
        port: int,
        use_ssl: bool,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ) -> None:
        scheme = b"https" if use_ssl else b"http"
        origin = httpcore.URL(
            scheme=scheme,
            host=ip.encode("utf-8"),
            port=port,
        )
        ssl_context = ssl.create_default_context() if use_ssl else None
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            retries=0,
        )
        self._origin = origin
        self._hostname = hostname

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.AsyncByteStream)
        body = request.stream

        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=self._origin.scheme,
                host=self._origin.host,
                port=self._origin.port,
                target=request.url.raw_path,
            ),
            headers=[(k.encode("latin-1"), v.encode("latin-1")) for k, v in request.headers.items()],
            content=body,
            extensions={"sni_hostname": self._hostname},
        )
        core_response = await self._pool.handle_async_request(core_request)
        try:
            from httpx._transports.default import AsyncResponseStream
        except ImportError:  # pragma: no cover - httpx version drift
            from httpx._transports.default import ResponseStream as AsyncResponseStream  # type: ignore[no-redef]
        return httpx.Response(
            status_code=core_response.status,
            headers=[(k.decode("latin-1"), v.decode("latin-1")) for k, v in core_response.headers],
            stream=AsyncResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


# Cache of pinned transports keyed by (hostname, port, use_ssl, ip).
_pinned_transport_cache: dict[tuple[str, int, bool, str], _PinnedIPTransport] = {}


def pinned_transport_for(target: PinnedTarget, ip: str | None = None) -> httpx.AsyncBaseTransport:
    """Return a cached, pinned transport for *target*.

    Connections are keyed to a single validated IP, eliminating the
    resolve→connect TOCTOU window that enables DNS rebinding.
    """
    use_ssl = target.url.lower().startswith("https://")
    pinned_ip = ip or target.ips[0]
    key = (target.hostname, target.port, use_ssl, pinned_ip)
    transport = _pinned_transport_cache.get(key)
    if transport is None:
        transport = _PinnedIPTransport(
            hostname=target.hostname,
            ip=pinned_ip,
            port=target.port,
            use_ssl=use_ssl,
        )
        _pinned_transport_cache[key] = transport
    return transport


async def close_pinned_transports() -> None:
    """Close all cached pinned transports (used on shutdown/tests)."""
    for transport in list(_pinned_transport_cache.values()):
        try:
            await transport.aclose()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Error closing pinned transport", exc_info=True)
    _pinned_transport_cache.clear()
