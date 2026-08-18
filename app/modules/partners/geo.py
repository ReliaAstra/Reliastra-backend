"""Country-level geo resolution from a local MaxMind GeoLite2 database.

Design constraints this module exists to satisfy:

* **No per-request external GeoIP call.** Lookups hit a memory-mapped local
  ``.mmdb`` file. If the file is missing, resolution degrades to ``None``
  and the request continues — geo is analytics, never a gate.
* **Country only.** We read ``country_code`` and ``country_name`` and
  nothing else. City, subdivision, postcode and coordinates are available in
  the database and are deliberately not extracted or stored.
* **No raw IPs at rest.** The persistent cache is keyed by the HMAC of the
  IP (:func:`app.modules.partners.utils.hash_ip`), so the cache cannot be
  used to reconstruct visitor addresses.

The reader is opened once per process and reused; ``maxminddb`` readers are
thread-safe for concurrent lookups.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.partners.models import GeoIpCache
from app.modules.partners.repository import GeoRepository
from app.modules.partners.utils import hash_ip

logger = logging.getLogger(__name__)

_reader: Any | None = None
_reader_path: str | None = None
_reader_failed: bool = False


@dataclass(frozen=True)
class GeoResult:
    """Resolved location. Both fields are ``None`` when unknown."""

    country_code: str | None = None
    country_name: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.country_code is not None


UNKNOWN = GeoResult()


def _open_reader() -> Any | None:
    """Open (and memoise) the local GeoLite2 reader.

    A missing database is logged once at INFO and then treated as a
    permanent, silent no-op: an unconfigured geo database must never turn
    into per-request log spam or an error surface.
    """
    global _reader, _reader_path, _reader_failed

    path = settings.MAXMIND_DB_PATH
    if _reader is not None and _reader_path == path:
        return _reader
    if _reader_failed and _reader_path == path:
        return None

    _reader_path = path
    if not path or not os.path.exists(path):
        _reader_failed = True
        logger.info(
            "MaxMind database not present at %s; geo resolution disabled", path
        )
        return None

    try:
        import maxminddb

        _reader = maxminddb.open_database(path)
        _reader_failed = False
        logger.info("MaxMind database loaded from %s", path)
        return _reader
    except Exception as exc:  # pragma: no cover - environment dependent
        _reader_failed = True
        logger.warning("Failed to open MaxMind database at %s: %s", path, exc)
        return None


def reset_reader() -> None:
    """Drop the cached reader (used by tests and after a database refresh)."""
    global _reader, _reader_path, _reader_failed
    try:
        if _reader is not None:
            _reader.close()
    except Exception:  # pragma: no cover - defensive
        pass
    _reader = None
    _reader_path = None
    _reader_failed = False


def database_available() -> bool:
    return _open_reader() is not None


def database_metadata() -> dict[str, Any]:
    """Build info for the admin coverage endpoint."""
    reader = _open_reader()
    if reader is None:
        return {"available": False, "path": settings.MAXMIND_DB_PATH}
    try:
        meta = reader.metadata()
        return {
            "available": True,
            "path": settings.MAXMIND_DB_PATH,
            "build_epoch": int(meta.build_epoch),
            "database_type": meta.database_type,
            "node_count": meta.node_count,
        }
    except Exception:  # pragma: no cover - defensive
        return {"available": True, "path": settings.MAXMIND_DB_PATH}


def _is_public_ip(ip: str) -> bool:
    """Private, loopback and reserved ranges are never worth resolving."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_reserved
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
    )


def lookup_ip(ip: str | None) -> GeoResult:
    """Synchronous, local-only country lookup. Never raises."""
    if not ip or not _is_public_ip(ip):
        return UNKNOWN
    reader = _open_reader()
    if reader is None:
        return UNKNOWN
    try:
        record = reader.get(ip)
    except Exception as exc:  # pragma: no cover - corrupt db / bad input
        logger.debug("MaxMind lookup failed for hashed ip: %s", exc)
        return UNKNOWN
    if not isinstance(record, dict):
        return UNKNOWN

    # GeoLite2-City and GeoLite2-Country share the `country` structure; fall
    # back to `registered_country` when the record has no country assignment.
    country = record.get("country") or record.get("registered_country") or {}
    if not isinstance(country, dict):
        return UNKNOWN
    code = country.get("iso_code")
    names = country.get("names") if isinstance(country.get("names"), dict) else {}
    name = names.get("en") if names else None
    if not code:
        return UNKNOWN
    return GeoResult(country_code=str(code).upper()[:2], country_name=name)


class GeoService:
    """Cached geo resolution backed by ``geo_ip_cache``.

    The cache exists to keep the click path cheap and to make country
    analytics reproducible; it stores only the hashed IP and the resolved
    country.
    """

    @staticmethod
    async def resolve(
        session: AsyncSession, ip: str | None, *, use_cache: bool = True
    ) -> GeoResult:
        if not ip:
            return UNKNOWN

        ip_digest = hash_ip(ip)
        if ip_digest is None:
            return UNKNOWN

        now = datetime.now(timezone.utc)
        ttl = timedelta(seconds=max(60, settings.MAXMIND_CACHE_TTL_SECONDS))

        if use_cache:
            cached = await GeoRepository.get_cached(session, ip_digest)
            if cached is not None:
                looked_up = cached.looked_up_at
                if looked_up is not None and looked_up.tzinfo is None:
                    looked_up = looked_up.replace(tzinfo=timezone.utc)
                if looked_up is not None and now - looked_up < ttl:
                    return GeoResult(
                        country_code=cached.country_code,
                        country_name=cached.country_name,
                    )

        result = lookup_ip(ip)

        # Negative results are cached too — an unresolvable IP should not be
        # re-read from the database on every single click.
        try:
            await GeoRepository.upsert_cached(
                session,
                GeoIpCache(
                    ip_hash=ip_digest,
                    country_code=result.country_code,
                    country_name=result.country_name,
                    source="maxmind" if result.is_resolved else "unresolved",
                    looked_up_at=now,
                ),
            )
        except Exception as exc:  # pragma: no cover - cache must never break a click
            logger.debug("Geo cache write skipped: %s", exc)

        return result

    @staticmethod
    async def coverage(session: AsyncSession) -> dict[str, Any]:
        total, countries, unresolved = await GeoRepository.cache_stats(session)
        meta = database_metadata()
        build_epoch = meta.get("build_epoch")
        age_days = None
        if build_epoch:
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(
                build_epoch, tz=timezone.utc
            )
            age_days = age.days
        return {
            "database_available": bool(meta.get("available")),
            "database_path": meta.get("path", settings.MAXMIND_DB_PATH),
            "database_build_epoch": build_epoch,
            "database_age_days": age_days,
            "cached_lookups": total,
            "resolved_countries": countries,
            "unresolved_lookups": unresolved,
        }


geo_service = GeoService()

__all__ = [
    "GeoResult",
    "GeoService",
    "UNKNOWN",
    "database_available",
    "database_metadata",
    "geo_service",
    "lookup_ip",
    "reset_reader",
]
