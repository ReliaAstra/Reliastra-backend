"""Billing repository marker; Stripe persistence uses OrganizationService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
