"""Evidence generation policy."""

from __future__ import annotations

from app.modules.organizations.constants import Plan

EVIDENCE_PLANS = {Plan.STANDARD, Plan.PROFESSIONAL, Plan.AGENCY}
DOWNLOAD_URL_TTL_SECONDS = 3600
