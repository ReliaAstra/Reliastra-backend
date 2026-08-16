from __future__ import annotations

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vendors.models import VendorTracking

logger = logging.getLogger(__name__)

_BASE_URL = "https://reliastra.com"
_FEED_TITLE = "Reliastra Vendor Status Feed"
_FEED_SUBTITLE = "Real-time status monitoring for tracked vendors"

# In-memory cache: {(format_type, category): (xml_bytes, timestamp)}
_cache: dict[tuple[str, str | None], tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


class FeedService:
    """Generate Atom and RSS XML feeds for vendor status."""

    async def generate_vendor_feed(
        self,
        session: AsyncSession,
        format_type: str = "atom",
        category: str | None = None,
    ) -> str:
        """Generate a feed of all public vendors with their latest status."""
        format_type = format_type.lower().strip()
        cache_key = (format_type, category)

        # Check cache
        now = time.time()
        if cache_key in _cache:
            cached_xml, cached_ts = _cache[cache_key]
            if now - cached_ts < _CACHE_TTL_SECONDS:
                return cached_xml

        # Fetch vendors
        stmt = select(VendorTracking).where(VendorTracking.is_public.is_(True))
        if category:
            stmt = stmt.where(VendorTracking.category == category)
        stmt = stmt.order_by(VendorTracking.display_name.asc())

        result = await session.execute(stmt)
        vendors = list(result.scalars().all())

        # Build feed
        entries: list[dict[str, Any]] = []
        for vendor in vendors:
            status = self._determine_vendor_status(session, vendor)
            latest_ts = vendor.last_check_at or vendor.updated_at
            latency = self._get_vendor_latency(session, vendor)

            entry = {
                "title": f"{vendor.display_name}: {status} (latency: {latency}ms)",
                "id": f"urn:reliastra:vendor:{vendor.vendor_name}",
                "link": f"{_BASE_URL}/vendors/{vendor.vendor_name}",
                "updated": latest_ts or datetime.now(timezone.utc),
                "summary": (
                    f"Status: {status}. "
                    f"Category: {vendor.category}. "
                    f"Last checked: {(latest_ts or datetime.now(timezone.utc)).isoformat()}."
                ),
                "vendor_name": vendor.vendor_name,
                "display_name": vendor.display_name,
            }
            entries.append(entry)

        updated = max(
            (e["updated"] for e in entries),
            default=datetime.now(timezone.utc),
        )

        if format_type == "rss":
            xml_str = self._build_rss(entries, updated)
        else:
            xml_str = self._build_atom(entries, updated)

        # Update cache
        _cache[cache_key] = (xml_str, now)

        return xml_str

    async def generate_vendor_detail_feed(
        self,
        session: AsyncSession,
        vendor_name: str,
    ) -> str:
        """Generate an Atom feed for a single vendor with status changes and incidents."""
        result = await session.execute(
            select(VendorTracking).where(
                VendorTracking.vendor_name == vendor_name.lower(),
                VendorTracking.is_public.is_(True),
            )
        )
        vendor = result.scalar_one_or_none()

        if vendor is None:
            from app.core.exceptions import ResourceNotFoundException

            raise ResourceNotFoundException(f"Vendor '{vendor_name}' not found")

        # Fetch related incidents
        from app.modules.dependencies.models import Dependency
        from app.modules.incidents.models import Incident

        deps_result = await session.execute(
            select(Dependency).where(
                Dependency.endpoint_url == vendor.endpoint_url
            )
        )
        deps = list(deps_result.scalars().all())
        dep_ids = [d.id for d in deps]

        incidents = []
        if dep_ids:
            inc_result = await session.execute(
                select(Incident)
                .where(Incident.dependency_id.in_(dep_ids))
                .order_by(Incident.started_at.desc())
                .limit(20)
            )
            incidents = list(inc_result.scalars().all())

        entries: list[dict[str, Any]] = []

        # Vendor status entry
        status = self._determine_vendor_status(session, vendor)
        latency = self._get_vendor_latency(session, vendor)
        latest_ts = vendor.last_check_at or vendor.updated_at

        entries.append({
            "title": f"{vendor.display_name}: {status} (latency: {latency}ms)",
            "id": f"urn:reliastra:vendor:{vendor.vendor_name}:current",
            "link": f"{_BASE_URL}/vendors/{vendor.vendor_name}",
            "updated": latest_ts or datetime.now(timezone.utc),
            "summary": (
                f"Current status: {status}. "
                f"Category: {vendor.category}. "
                f"Last checked: {(latest_ts or datetime.now(timezone.utc)).isoformat()}."
            ),
        })

        # Incident entries
        for inc in incidents:
            severity_label = inc.severity.upper()
            resolved_label = " [RESOLVED]" if inc.resolved_at else " [ACTIVE]"
            inc_entries = {
                "title": f"{vendor.display_name}: {severity_label} incident{resolved_label} — {inc.description or inc.root_cause}",
                "id": f"urn:reliastra:incident:{inc.id}",
                "link": f"{_BASE_URL}/vendors/{vendor.vendor_name}#incident-{inc.id}",
                "updated": inc.resolved_at or inc.started_at,
                "summary": (
                    f"Severity: {inc.severity}. "
                    f"Status: {inc.status}. "
                    f"Started: {inc.started_at.isoformat()}."
                    + (f" Resolved: {inc.resolved_at.isoformat()}." if inc.resolved_at else "")
                ),
            }
            entries.append(inc_entries)

        updated = max(
            (e["updated"] for e in entries),
            default=datetime.now(timezone.utc),
        )

        return self._build_atom(entries, updated, feed_title=f"{vendor.display_name} Status Feed")

    def get_etag(self, xml_str: str) -> str:
        """Generate an ETag from the XML content."""
        h = hashlib.sha256(xml_str.encode("utf-8")).hexdigest()[:32]
        return f'W/"{h}"'

    def get_last_modified(self, xml_str: str) -> str:
        """Parse the most recent updated timestamp from the feed XML."""
        try:
            root = ET.fromstring(xml_str)
            # Atom: <updated>
            updated = root.find("{http://www.w3.org/2005/Atom}updated")
            if updated is not None and updated.text:
                return updated.text
            # RSS: <lastBuildDate>
            last_build = root.find("channel/lastBuildDate")
            if last_build is not None and last_build.text:
                return last_build.text
        except ET.ParseError:
            pass
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    # ------------------------------------------------------------------
    # XML builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_atom(
        entries: list[dict[str, Any]],
        updated: datetime,
        feed_title: str | None = None,
    ) -> str:
        """Build an Atom 1.0 XML feed."""
        ns = "http://www.w3.org/2005/Atom"
        ET.register_namespace("", ns)

        feed = ET.Element(f"{{{ns}}}feed")

        title = ET.SubElement(feed, f"{{{ns}}}title")
        title.text = feed_title or _FEED_TITLE

        subtitle = ET.SubElement(feed, f"{{{ns}}}subtitle")
        subtitle.text = _FEED_SUBTITLE

        link_self = ET.SubElement(feed, f"{{{ns}}}link")
        link_self.set("href", f"{_BASE_URL}/feed/vendors")
        link_self.set("rel", "self")

        link_alt = ET.SubElement(feed, f"{{{ns}}}link")
        link_alt.set("href", _BASE_URL)

        id_elem = ET.SubElement(feed, f"{{{ns}}}id")
        id_elem.text = f"urn:reliastra:feed:vendors"

        updated_elem = ET.SubElement(feed, f"{{{ns}}}updated")
        updated_elem.text = updated.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        for entry in entries:
            entry_elem = ET.SubElement(feed, f"{{{ns}}}entry")

            e_title = ET.SubElement(entry_elem, f"{{{ns}}}title")
            e_title.text = entry["title"]

            e_id = ET.SubElement(entry_elem, f"{{{ns}}}id")
            e_id.text = entry["id"]

            e_link = ET.SubElement(entry_elem, f"{{{ns}}}link")
            e_link.set("href", entry["link"])

            e_updated = ET.SubElement(entry_elem, f"{{{ns}}}updated")
            e_updated.text = entry["updated"].strftime("%Y-%m-%dT%H:%M:%S+00:00")

            e_summary = ET.SubElement(entry_elem, f"{{{ns}}}summary")
            e_summary.text = entry["summary"]

        return ET.tostring(feed, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _build_rss(
        entries: list[dict[str, Any]],
        updated: datetime,
    ) -> str:
        """Build an RSS 2.0 XML feed."""
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")

        title = ET.SubElement(channel, "title")
        title.text = _FEED_TITLE

        description = ET.SubElement(channel, "description")
        description.text = _FEED_SUBTITLE

        link = ET.SubElement(channel, "link")
        link.text = _BASE_URL

        language = ET.SubElement(channel, "language")
        language.text = "en-us"

        last_build = ET.SubElement(channel, "lastBuildDate")
        last_build.text = updated.strftime("%a, %d %b %Y %H:%M:%S GMT")

        generator = ET.SubElement(channel, "generator")
        generator.text = "Reliastra Feed Generator"

        for entry in entries:
            item = ET.SubElement(channel, "item")

            i_title = ET.SubElement(item, "title")
            i_title.text = entry["title"]

            i_link = ET.SubElement(item, "link")
            i_link.text = entry["link"]

            i_guid = ET.SubElement(item, "guid")
            i_guid.set("isPermaLink", "false")
            i_guid.text = entry["id"]

            i_desc = ET.SubElement(item, "description")
            i_desc.text = entry["summary"]

            i_pub = ET.SubElement(item, "pubDate")
            i_pub.text = entry["updated"].strftime("%a, %d %b %Y %H:%M:%S GMT")

        return ET.tostring(rss, encoding="unicode", xml_declaration=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _determine_vendor_status(
        session: AsyncSession,
        vendor: VendorTracking,
    ) -> str:
        """Quick check to determine vendor operational status."""
        from app.modules.observations.models import Observation

        result = await session.execute(
            select(Observation)
            .where(Observation.endpoint_url == vendor.endpoint_url)
            .order_by(Observation.timestamp.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            return "unknown"
        if latest.error_type or latest.status_code is None:
            return "degraded"
        if latest.status_code >= 500:
            return "down"
        if latest.status_code >= 400:
            return "degraded"
        return "operational"

    @staticmethod
    async def _get_vendor_latency(
        session: AsyncSession,
        vendor: VendorTracking,
    ) -> int:
        """Get the latest latency for a vendor (rounded to int ms)."""
        from app.modules.observations.models import Observation

        result = await session.execute(
            select(Observation.latency_ms)
            .where(Observation.endpoint_url == vendor.endpoint_url)
            .order_by(Observation.timestamp.desc())
            .limit(1)
        )
        val = result.scalar_one_or_none()
        return round(val) if val is not None else 0


feed_service = FeedService()
