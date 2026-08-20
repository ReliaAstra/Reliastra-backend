from __future__ import annotations

import asyncio
import html as html_mod
import logging
import time
from xml.sax.saxutils import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.badges.repository import BadgeRepository
from app.modules.badges.schemas import BadgeEmbedResponse, BadgeStyle
from app.modules.vendors.service import vendor_service

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Status-to-colour mapping
# ------------------------------------------------------------------

_STATUS_COLORS: dict[str, str] = {
    "up": "#2ea043",
    "operational": "#2ea043",
    "degraded": "#d29922",
    "down": "#f85149",
    "outage": "#f85149",
    "unknown": "#8b949e",
    "maintenance": "#1f6feb",
}

_STATUS_LABELS: dict[str, str] = {
    "up": "Operational",
    "operational": "Operational",
    "degraded": "Degraded",
    "down": "Down",
    "outage": "Outage",
    "unknown": "Unknown",
    "maintenance": "Maintenance",
}

# ------------------------------------------------------------------
# In-memory TTL cache for badge SVGs
# ------------------------------------------------------------------

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[str, float]] = {}


def _cache_get(key: str) -> str | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    svg, ts = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return svg


def _cache_set(key: str, svg: str) -> None:
    _cache[key] = (svg, time.monotonic())


# ------------------------------------------------------------------
# SVG generation helpers
# ------------------------------------------------------------------


def _escape(text: str) -> str:
    """XML-escape a string for safe embedding in SVG attributes/text."""
    return escape(text)


def _svg_flat(
    label: str,
    value: str,
    color: str,
    show_latency: bool = False,
    latency_ms: float | None = None,
) -> str:
    """Standard shields.io flat badge (20px height)."""
    label_text = _escape(label)
    value_text = _escape(value)
    if show_latency and latency_ms is not None:
        value_text += f" {latency_ms:.0f}ms"

    # Approximate character widths (monospace-ish for SVG)
    label_w = max(len(label_text) * 6.5 + 20, 10)
    value_w = max(len(value_text) * 6.5 + 20, 10)
    total_w = label_w + value_w
    h = 20

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}" '
        f'role="img" aria-label="{label_text}: {value_text}">'
        f'<title>{label_text}: {value_text}</title>'
        f'<linearGradient id="a" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/> '
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<rect width="{total_w:.0f}" height="{h}" rx="3" fill="#555"/> '
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" fill="{color}"/> '
        f'<rect width="{total_w:.0f}" height="{h}" rx="3" fill="url(#a)"/> '
        f'<text x="{label_w / 2:.1f}" y="{h / 2 + 4:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{label_text}</text> '
        f'<text x="{label_w + value_w / 2:.1f}" y="{h / 2 + 4:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{value_text}</text>'
        f'</svg>'
    )


def _svg_for_the_badge(
    label: str,
    value: str,
    color: str,
    show_latency: bool = False,
    latency_ms: float | None = None,
) -> str:
    """Taller (28px), all-caps, larger text badge."""
    label_text = _escape(label.upper())
    value_text = _escape(value.upper())
    if show_latency and latency_ms is not None:
        value_text += f" {latency_ms:.0f}MS"

    label_w = max(len(label_text) * 7.5 + 24, 10)
    value_w = max(len(value_text) * 7.5 + 24, 10)
    total_w = label_w + value_w
    h = 28

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}" '
        f'role="img" aria-label="{label_text}: {value_text}">'
        f'<title>{label_text}: {value_text}</title>'
        f'<rect width="{total_w:.0f}" height="{h}" rx="0" fill="#555"/> '
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" fill="{color}"/> '
        f'<text x="{label_w / 2:.1f}" y="{h / 2 + 5:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="13" font-weight="bold">{label_text}</text> '
        f'<text x="{label_w + value_w / 2:.1f}" y="{h / 2 + 5:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="13" font-weight="bold">{value_text}</text>'
        f'</svg>'
    )


def _svg_plastic(
    label: str,
    value: str,
    color: str,
    show_latency: bool = False,
    latency_ms: float | None = None,
) -> str:
    """Plastic style with subtle gradient overlay and rounded corners."""
    label_text = _escape(label)
    value_text = _escape(value)
    if show_latency and latency_ms is not None:
        value_text += f" {latency_ms:.0f}ms"

    label_w = max(len(label_text) * 6.5 + 20, 10)
    value_w = max(len(value_text) * 6.5 + 20, 10)
    total_w = label_w + value_w
    h = 18

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}" '
        f'role="img" aria-label="{label_text}: {value_text}">'
        f'<title>{label_text}: {value_text}</title>'
        f'<linearGradient id="b" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".1"/> '
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<linearGradient id="c" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".2"/> '
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<rect width="{total_w:.0f}" height="{h}" rx="4" fill="#555"/> '
        f'<rect width="{total_w:.0f}" height="{h}" rx="4" fill="url(#c)"/> '
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" fill="{color}"/> '
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" rx="4" fill="url(#b)"/> '
        f'<text x="{label_w / 2:.1f}" y="{h / 2 + 3.5:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{label_text}</text> '
        f'<text x="{label_w + value_w / 2:.1f}" y="{h / 2 + 3.5:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{value_text}</text>'
        f'</svg>'
    )


def _svg_social(
    label: str,
    value: str,
    color: str,
    show_latency: bool = False,
    latency_ms: float | None = None,
) -> str:
    """Social style: wider badge with vendor icon placeholder + status."""
    label_text = _escape(label)
    value_text = _escape(value)
    if show_latency and latency_ms is not None:
        value_text += f" {latency_ms:.0f}ms"

    # Social badges are wider and taller
    icon_w = 30
    label_w = max(len(label_text) * 6.5 + 16, 40)
    value_w = max(len(value_text) * 6.5 + 24, 10)
    total_w = icon_w + label_w + value_w
    h = 20

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}" '
        f'role="img" aria-label="{label_text}: {value_text}">'
        f'<title>{label_text}: {value_text}</title>'
        f'<linearGradient id="d" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/> '
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<rect width="{total_w:.0f}" height="{h}" rx="3" fill="#555"/> '
        f'<rect x="{icon_w + label_w:.0f}" width="{value_w:.0f}" height="{h}" fill="{color}"/> '
        f'<rect width="{total_w:.0f}" height="{h}" rx="3" fill="url(#d)"/> '
        f'<circle cx="{icon_w / 2:.1f}" cy="{h / 2:.1f}" r="{min(6, icon_w / 2 - 2):.0f}" fill="#fff" opacity=".7"/> '
        f'<text x="{icon_w + label_w / 2:.1f}" y="{h / 2 + 4:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{label_text}</text> '
        f'<text x="{icon_w + label_w + value_w / 2:.1f}" y="{h / 2 + 4:.1f}" fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">{value_text}</text>'
        f'</svg>'
    )


_STYLE_RENDERERS = {
    BadgeStyle.flat: _svg_flat,
    BadgeStyle.for_the_badge: _svg_for_the_badge,
    BadgeStyle.plastic: _svg_plastic,
    BadgeStyle.social: _svg_social,
}


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


class BadgeService:
    def __init__(self) -> None:
        self.repository = BadgeRepository()

    async def generate_badge_svg(
        self,
        session: AsyncSession,
        vendor_name: str,
        style: str,
        label: str,
        show_latency: bool,
    ) -> tuple[str, str, str]:
        """Generate an SVG badge for a vendor.

        Returns ``(svg_content, status, display_name)``.
        """
        # Resolve style enum
        try:
            badge_style = BadgeStyle(style)
        except ValueError:
            badge_style = BadgeStyle.flat

        # Check in-memory cache
        cache_key = f"{vendor_name}:{badge_style.value}:{label}:{show_latency}"
        cached_svg = _cache_get(cache_key)

        # Look up vendor and determine status + latency
        vendor = await vendor_service.repository.get_by_name(session, vendor_name)
        if not vendor or not vendor.is_public:
            status = "unknown"
            display_name = vendor_name
            latency_ms: float | None = None
        else:
            display_name = vendor.display_name
            latency_ms = None

            # Fetch latest observation for this vendor
            from app.modules.vendors.repository import VendorRepository
            endpoints = await VendorRepository.list_vendor_endpoints(
                session, vendor.vendor_name
            )
            urls = list(
                dict.fromkeys(
                    [vendor.endpoint_url]
                    + [ep.endpoint_url for ep in endpoints]
                )
            )

            from app.modules.observations.repository import ObservationRepository
            latest = await ObservationRepository.get_latest_observation(
                session, urls
            )

            if latest:
                if latest.status_code is not None and latest.error_type is None:
                    status = "operational"
                    latency_ms = latest.latency_ms
                else:
                    status = "degraded"
            else:
                status = "unknown"

        color = _STATUS_COLORS.get(status, "#8b949e")
        value_text = _STATUS_LABELS.get(status, "Unknown")

        renderer = _STYLE_RENDERERS.get(badge_style, _svg_flat)
        svg = renderer(label, value_text, color, show_latency, latency_ms)

        # Cache the SVG
        _cache_set(cache_key, svg)

        return svg, status, display_name

    async def get_embed_code(
        self,
        session: AsyncSession,
        vendor_name: str,
        style: str = "flat",
        label: str = "Reliastra",
        show_latency: bool = False,
        base_url: str = "https://reliastra.com",
    ) -> BadgeEmbedResponse:
        """Build the badge URL, HTML img tag, and markdown snippet."""
        svg, status, display_name = await self.generate_badge_svg(
            session, vendor_name, style, label, show_latency
        )

        params: list[str] = [f"style={style}", f"label={label}"]
        if show_latency:
            params.append("show_latency=true")
        qs = "&amp;".join(params)
        url = f"{base_url}/v1/public/vendors/{vendor_name}/badge.svg?{qs}"

        html = (
            f'<img src="{html_mod.escape(url)}" alt="{html_mod.escape(display_name)} status: {html_mod.escape(status)}">'
        )
        markdown = f"![{display_name} status: {status}]({url})"

        return BadgeEmbedResponse(
            html=html,
            markdown=markdown,
            url=url,
            vendor_name=vendor_name,
            display_name=display_name,
            status=status,
        )

    async def record_impression(
        self,
        session: AsyncSession,
        vendor_name: str,
        ip_hash: str,
        utm_source: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> None:
        """Insert a badge impression row (non-blocking fire-and-forget)."""
        try:
            await self.repository.create_impression(
                session=session,
                vendor_name=vendor_name,
                ip_hash=ip_hash,
                utm_source=utm_source,
                user_agent=user_agent,
                referer=referer,
            )
            await session.commit()
        except Exception:
            logger.debug(
                "Failed to record badge impression for %s", vendor_name,
                exc_info=True,
            )
            # Never let impression recording failures propagate

    async def record_impression_bg(
        self,
        vendor_name: str,
        ip_hash: str,
        utm_source: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> None:
        """Fire-and-forget impression recording with its own DB session."""
        try:
            from app.db.session import get_session_maker
            session_maker = get_session_maker()
            async with session_maker() as session:
                try:
                    await self.repository.create_impression(
                        session=session,
                        vendor_name=vendor_name,
                        ip_hash=ip_hash,
                        utm_source=utm_source,
                        user_agent=user_agent,
                        referer=referer,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.debug(
                        "Failed to record badge impression for %s",
                        vendor_name,
                        exc_info=True,
                    )
        except Exception:
            logger.debug(
                "Failed to open session for badge impression for %s",
                vendor_name,
                exc_info=True,
            )


badge_service = BadgeService()
