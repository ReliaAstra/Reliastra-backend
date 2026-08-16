from __future__ import annotations

import io
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.timeline_share.repository import TimelineShareRepository
from app.modules.timeline_share.schemas import (
    TimelineShareCreateRequest,
    TimelineShareResponse,
)
from app.modules.vendors.schemas import TimelineBucket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory PNG cache: keyed by (vendor_name, window, region), stores
# (png_bytes, timestamp).  Entries expire after 5 minutes.
# ---------------------------------------------------------------------------
_png_cache: dict[tuple[str, str, str], tuple[bytes, float]] = {}
_PNG_CACHE_TTL_SECONDS = 300  # 5 minutes

# Chart colour palette (dark theme)
_BG_COLOR = "#0d1117"
_GRID_COLOR = "#21262d"
_TEXT_COLOR = "#c9d1d9"
_LATENCY_COLOR = "#58a6ff"
_AVAIL_UP_COLOR = "#238636"
_AVAIL_DOWN_COLOR = "#da3633"
_INCIDENT_COLOR = "#f85149"

# Frontend base URL for QR codes and share links
_FRONTEND_TRACK_BASE = "https://frontend.zevcloud.app/track"


class TimelineShareService:
    """Service for generating shareable timeline PNG images and managing
    short-lived share links.
    """

    # ------------------------------------------------------------------
    # PNG generation
    # ------------------------------------------------------------------

    async def generate_timeline_png(
        self,
        session: AsyncSession,
        vendor_name: str,
        window: str,
        region: str,
        width: int = 1200,
        height: int = 630,
        include_qr: bool = True,
        utm_source: str | None = None,
    ) -> tuple[bytes, str]:
        """Generate a timeline PNG for a vendor.

        Returns ``(png_bytes, content_type)`` where *content_type* is
        always ``"image/png"``.
        """
        # --- Check in-memory cache ---
        cache_key = (vendor_name.lower(), window, region)
        cached = _png_cache.get(cache_key)
        if cached is not None:
            cached_bytes, cached_ts = cached
            if time.monotonic() - cached_ts < _PNG_CACHE_TTL_SECONDS:
                return cached_bytes, "image/png"
            # Expired — evict
            del _png_cache[cache_key]

        # --- Fetch timeline data via vendor service ---
        timeline_data = await self._fetch_timeline_data(
            session, vendor_name, window, region
        )

        # --- Resolve vendor display name ---
        display_name = await self._get_vendor_display_name(session, vendor_name)

        # --- Render chart ---
        png_bytes = await self._render_chart(
            display_name=display_name,
            window=window,
            region=region,
            width=width,
            height=height,
            include_qr=include_qr,
            utm_source=utm_source,
            vendor_name=vendor_name,
            points=timeline_data.get("points", []),
        )

        # --- Cache ---
        _png_cache[cache_key] = (png_bytes, time.monotonic())
        # Prune stale entries to prevent unbounded memory growth
        self._prune_cache()

        return png_bytes, "image/png"

    # ------------------------------------------------------------------
    # Share link management
    # ------------------------------------------------------------------

    async def create_share_link(
        self,
        session: AsyncSession,
        vendor_name: str,
        user_id: uuid.UUID | None,
        request: TimelineShareCreateRequest,
        base_url: str = "https://frontend.zevcloud.app",
    ) -> TimelineShareResponse:
        """Create a short-lived share link for a vendor timeline PNG."""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        share = await TimelineShareRepository.create_share(
            session,
            vendor_name=vendor_name.lower(),
            user_id=user_id,
            share_token=token,
            window=request.window,
            region=request.region,
            note=request.note,
            utm_source=None,
            view_count=0,
            expires_at=expires_at,
        )

        share_url = (
            f"{base_url}/shared/timeline/{share.vendor_name}"
            f"?token={share.share_token}&window={share.window}&region={share.region}"
        )

        return TimelineShareResponse(
            share_url=share_url,
            expires_at=expires_at,
            share_token=token,
            vendor_name=share.vendor_name,
        )

    # ------------------------------------------------------------------
    # Event tracking
    # ------------------------------------------------------------------

    async def record_share_event(
        self,
        session: AsyncSession,
        vendor_name: str,
        user_id: uuid.UUID | None,
        utm_source: str | None,
    ) -> None:
        """Record an analytics event when a shared timeline is viewed.

        This is a fire-and-forget method — errors are logged but not raised.
        """
        try:
            await TimelineShareRepository.create_share(
                session,
                vendor_name=vendor_name.lower(),
                user_id=user_id,
                share_token=secrets.token_urlsafe(32),
                window="24h",
                region="us-east",
                utm_source=utm_source,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        except Exception:
            logger.exception(
                "Failed to record share event for vendor=%s", vendor_name
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_timeline_data(
        session: AsyncSession,
        vendor_name: str,
        window: str,
        region: str,
    ) -> dict[str, Any]:
        """Fetch timeline data using the vendor service."""
        from app.modules.vendors.service import vendor_service

        response = await vendor_service.get_vendor_timeline(
            session, vendor_name, window=window, region=region
        )
        return {
            "vendor_name": response.vendor_name,
            "window": response.window,
            "region": response.region,
            "from": response.from_,
            "to": response.to,
            "current": response.current,
            "points": response.points,
        }

    @staticmethod
    async def _get_vendor_display_name(
        session: AsyncSession,
        vendor_name: str,
    ) -> str:
        """Look up the human-friendly display name for a vendor."""
        from app.modules.vendors.repository import VendorRepository

        vendor = await VendorRepository.get_by_name(session, vendor_name)
        if vendor:
            return vendor.display_name
        return vendor_name.replace("-", " ").title()

    @staticmethod
    def _prune_cache() -> None:
        """Remove expired entries from the in-memory PNG cache."""
        now = time.monotonic()
        stale = [
            k for k, (_, ts) in _png_cache.items()
            if now - ts >= _PNG_CACHE_TTL_SECONDS
        ]
        for k in stale:
            del _png_cache[k]

    @staticmethod
    def _render_chart(
        *,
        display_name: str,
        window: str,
        region: str,
        width: int,
        height: int,
        include_qr: bool,
        utm_source: str | None,
        vendor_name: str,
        points: list[TimelineBucket],
    ) -> bytes:
        """Render the timeline chart to PNG bytes using matplotlib.

        This method MUST be called with the ``Agg`` backend already set.
        """
        # matplotlib.use('Agg') is called at module import time, but we
        # defensively ensure it here as well.
        import matplotlib
        matplotlib.use("Agg")

        import matplotlib.dates as mdates
        import matplotlib.figure as mfig
        from matplotlib.ticker import FuncFormatter
        from PIL import Image as PILImage

        # ---- Prepare data arrays ----
        timestamps: list[datetime] = []
        latencies: list[float] = []
        is_up: list[bool] = []
        incident_indices: list[int] = []

        for idx, point in enumerate(points):
            timestamps.append(point.timestamp)
            latencies.append(point.avg_latency_ms)
            is_up.append(point.is_up)
            if point.incident_id is not None:
                incident_indices.append(idx)

        if not timestamps:
            # Fallback: generate a single "no data" placeholder chart
            timestamps = [
                datetime.now(timezone.utc) - timedelta(hours=24),
                datetime.now(timezone.utc),
            ]
            latencies = [0.0, 0.0]
            is_up = [True, True]

        # ---- Create figure ----
        dpi = 150
        fig_width = width / dpi
        fig_height = height / dpi

        fig = mfig.Figure(
            figsize=(fig_width, fig_height),
            dpi=dpi,
            facecolor=_BG_COLOR,
            constrained_layout=True,
        )

        # ---- Latency axis (top) ----
        ax_latency = fig.add_axes([0.08, 0.35, 0.84, 0.50])
        ax_latency.set_facecolor(_BG_COLOR)
        ax_latency.tick_params(colors=_TEXT_COLOR, labelsize=8)
        ax_latency.spines["bottom"].set_color(_GRID_COLOR)
        ax_latency.spines["left"].set_color(_GRID_COLOR)
        ax_latency.spines["top"].set_visible(False)
        ax_latency.spines["right"].set_visible(False)
        ax_latency.yaxis.label.set_color(_TEXT_COLOR)
        ax_latency.yaxis.label.set_size(9)

        # Plot latency line
        ax_latency.plot(
            timestamps,
            latencies,
            color=_LATENCY_COLOR,
            linewidth=1.5,
            alpha=0.9,
            zorder=3,
        )
        ax_latency.fill_between(
            timestamps,
            latencies,
            alpha=0.08,
            color=_LATENCY_COLOR,
            zorder=2,
        )
        ax_latency.set_ylabel("Latency (ms)", fontsize=9, color=_TEXT_COLOR)
        ax_latency.set_title(
            f"{display_name} — Status Timeline (last {window})",
            fontsize=14,
            color=_TEXT_COLOR,
            fontweight="bold",
            pad=10,
        )
        ax_latency.grid(True, color=_GRID_COLOR, alpha=0.5, linewidth=0.5)
        ax_latency.xaxis.set_visible(False)

        # Y-axis formatter: show "ms"
        ax_latency.yaxis.set_major_formatter(
            FuncFormatter(lambda val, _: f"{val:.0f}")
        )

        # ---- Availability band (bottom) ----
        ax_avail = fig.add_axes([0.08, 0.15, 0.84, 0.15])
        ax_avail.set_facecolor(_BG_COLOR)
        ax_avail.tick_params(colors=_TEXT_COLOR, labelsize=8)
        ax_avail.spines["bottom"].set_color(_GRID_COLOR)
        ax_avail.spines["left"].set_color(_GRID_COLOR)
        ax_avail.spines["top"].set_visible(False)
        ax_avail.spines["right"].set_visible(False)
        ax_avail.set_yticks([0, 1])
        ax_avail.set_yticklabels(["Down", "Up"], fontsize=7, color=_TEXT_COLOR)
        ax_avail.set_ylim(-0.1, 1.1)

        # Colour each segment green or red
        for i in range(len(timestamps)):
            colour = _AVAIL_UP_COLOR if is_up[i] else _AVAIL_DOWN_COLOR
            if i < len(timestamps) - 1:
                ax_avail.axvspan(
                    timestamps[i], timestamps[i + 1],
                    color=colour, alpha=0.6, zorder=1,
                )
            else:
                # Last point: small span
                ax_avail.axvspan(
                    timestamps[i],
                    timestamps[i] + timedelta(minutes=1),
                    color=colour, alpha=0.6, zorder=1,
                )

        # X-axis formatting with time
        ax_avail.xaxis.set_major_formatter(
            mdates.DateFormatter("%H:%M")
        )
        ax_avail.grid(True, color=_GRID_COLOR, alpha=0.3, linewidth=0.5, axis="x")

        # ---- Incident markers ----
        if incident_indices:
            inc_timestamps = [timestamps[i] for i in incident_indices]
            inc_latencies = [latencies[i] for i in incident_indices]
            ax_latency.scatter(
                inc_timestamps,
                inc_latencies,
                marker="v",
                c=_INCIDENT_COLOR,
                s=60,
                zorder=5,
                edgecolors="white",
                linewidths=0.5,
            )

        # ---- QR Code ----
        if include_qr:
            try:
                import qrcode

                qr_url = (
                    f"{_FRONTEND_TRACK_BASE}/{vendor_name}"
                    f"?utm_source=share_png"
                )
                if utm_source:
                    qr_url += f"&utm_source={utm_source}"

                qr = qrcode.make(qr_url, box_size=4, border=1)
                qr_img = qr.get_image()
                # Convert to RGBA and paste into figure
                qr_pil = PILImage.frombytes(
                    "RGBA", qr_img.size, qr_img.tobytes()
                )
                qr_buf = io.BytesIO()
                qr_pil.save(qr_buf, format="PNG")
                qr_buf.seek(0)

                from matplotlib.image import imread
                qr_arr = imread(qr_buf, format="png")
                # Place in bottom-right corner of the latency axis
                ax_latency.figimage(
                    qr_arr,
                    xo=fig_width * dpi - qr_arr.shape[1] - 20,
                    yo=15,
                    zorder=10,
                    alpha=0.85,
                )
            except Exception:
                logger.debug("QR code generation failed", exc_info=True)

        # ---- Footer ----
        footer_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fig.text(
            0.5, 0.02,
            f"Generated by Reliastra · {footer_ts}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#484f58",
            fontstyle="italic",
        )

        # ---- Region badge ----
        fig.text(
            0.92, 0.95,
            f"Region: {region}",
            ha="right",
            va="top",
            fontsize=8,
            color="#8b949e",
        )

        # ---- Render to bytes ----
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
        )
        buf.seek(0)
        png_bytes = buf.getvalue()

        # Clean up matplotlib figure to free memory
        import matplotlib.pyplot as plt
        plt.close(fig)

        return png_bytes


# Ensure matplotlib Agg backend is loaded before any rendering
import matplotlib
matplotlib.use("Agg")

timeline_share_service = TimelineShareService()
