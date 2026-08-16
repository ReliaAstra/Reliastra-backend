from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.modules.incidents.models import Incident
from app.modules.status_pages.models import StatusComponent
from app.modules.status_pages.repository import StatusPageRepository
from app.modules.status_pages.schemas import (
    PublicStatusResponse,
    StatusComponentResponse,
    StatusIncidentItem,
    StatusIncidentUpdate,
    StatusPageConfigRequest,
    StatusPageResponse,
)

logger = logging.getLogger(__name__)

_DEFAULT_COMPONENTS = [
    {
        "name": "api",
        "display_name": "API",
        "status": "operational",
        "description": "Core REST API endpoints",
        "order_index": 0,
    },
    {
        "name": "check_engine",
        "display_name": "Check Engine",
        "status": "operational",
        "description": "Scheduled vendor health checks and monitoring",
        "order_index": 1,
    },
    {
        "name": "dashboard",
        "display_name": "Dashboard",
        "status": "operational",
        "description": "Web dashboard and real-time status views",
        "order_index": 2,
    },
    {
        "name": "auth",
        "display_name": "Authentication",
        "status": "operational",
        "description": "OAuth, JWT, and API key authentication services",
        "order_index": 3,
    },
    {
        "name": "billing",
        "display_name": "Billing",
        "status": "operational",
        "description": "Subscription management and payment processing",
        "order_index": 4,
    },
]


class StatusPageService:
    """Service for managing status pages and public status views."""

    async def get_public_status(
        self, session: AsyncSession
    ) -> PublicStatusResponse:
        """Return overall Reliastra system health status."""
        components = await StatusPageRepository.list_public_components(session)

        component_responses = [
            StatusComponentResponse.model_validate(c) for c in components
        ]

        # Determine overall status from components
        status_priority = ["major_outage", "partial_outage", "degraded", "operational"]
        overall = "operational"
        for priority_status in status_priority:
            if any(c.status == priority_status for c in components):
                overall = priority_status
                break

        # Get active incidents (open, investigating, identified)
        active_incidents = await self._get_active_incidents(session)

        now = datetime.now(timezone.utc)

        return PublicStatusResponse(
            overall_status=overall,
            components=component_responses,
            active_incidents=active_incidents,
            last_updated=now,
            refresh_interval_seconds=60,
        )

    async def get_org_status_page(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> StatusPageResponse | None:
        """Get an organization's status page configuration."""
        page = await StatusPageRepository.get_by_org_id(session, org_id)
        if page is None:
            return None
        return StatusPageResponse.model_validate(page)

    async def create_org_status_page(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: StatusPageConfigRequest,
    ) -> StatusPageResponse:
        """Create a status page for an organization."""
        existing = await StatusPageRepository.get_by_org_id(session, org_id)
        if existing:
            raise ConflictException(
                "Organization already has a status page. Update it instead."
            )

        slug_exists = await StatusPageRepository.get_by_slug(session, request.slug)
        if slug_exists:
            raise ConflictException(
                f"Status page slug '{request.slug}' is already taken."
            )

        page = await StatusPageRepository.create(
            session=session,
            org_id=org_id,
            slug=request.slug,
            title=request.title,
            show_uptime_graph=request.show_uptime_graph,
            show_incident_history=request.show_incident_history,
            branding=request.branding,
            allowed_domains=request.allowed_domains,
        )

        logger.info("Created status page for org=%s slug=%s", org_id, request.slug)
        return StatusPageResponse.model_validate(page)

    async def get_public_status_page_by_slug(
        self, session: AsyncSession, slug: str
    ) -> dict:
        """Get a public status page by its slug (no auth required)."""
        page = await StatusPageRepository.get_by_slug(session, slug)
        if page is None:
            raise ResourceNotFoundException(
                f"Status page with slug '{slug}' not found"
            )

        # Combine page config with system status data
        system_status = await self.get_public_status(session)

        return {
            "page": StatusPageResponse.model_validate(page).model_dump(),
            "status": system_status.model_dump(),
        }

    async def seed_default_components(
        self, session: AsyncSession
    ) -> int:
        """Seed the default system components if they don't exist."""
        seeded = 0
        for comp_data in _DEFAULT_COMPONENTS:
            existing = await StatusPageRepository.get_component_by_name(
                session, comp_data["name"]
            )
            if not existing:
                await StatusPageRepository.upsert_component(session, **comp_data)
                seeded += 1
                logger.info("Seeded status component: %s", comp_data["name"])
        return seeded

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_active_incidents(
        session: AsyncSession,
    ) -> list[StatusIncidentItem]:
        """Fetch active system-level incidents for the public status page.

        Since incidents are org-scoped, we look for any open incidents across
        system components. For a platform-wide status page, we may want to show
        incidents tagged with specific root_cause values.
        """
        # For now, return an empty list — the status page focuses on components.
        # This can be extended to query platform-wide incidents.
        return []


status_page_service = StatusPageService()
