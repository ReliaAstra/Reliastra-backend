import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Subscription
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository


class BillingRepository:
    @staticmethod
    async def get_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Organization | None:
        return await OrganizationRepository.get_by_id(session, org_id)

    @staticmethod
    async def get_org_by_provider_customer(
        session: AsyncSession, provider: str, customer_id: str
    ) -> Organization | None:
        """Look up an organization by its provider customer id."""
        stmt = (
            select(Organization)
            .join(Subscription, Subscription.organization_id == Organization.id)
            .where(
                Subscription.provider == provider,
                Subscription.provider_customer_id == customer_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_org_plan(
        session: AsyncSession,
        org: Organization,
        plan: str,
        customer_id: str | None = None,
        subscription_id: str | None = None,
    ) -> Organization:
        kwargs: dict[str, Any] = {"plan": plan}
        if customer_id is not None:
            kwargs["stripe_customer_id"] = customer_id  # legacy column
        if subscription_id is not None:
            kwargs["stripe_subscription_id"] = subscription_id  # legacy column
        return await OrganizationRepository.update(session, org, **kwargs)

    # --- Subscription helpers -------------------------------------------------

    @staticmethod
    async def get_subscription(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(Subscription.organization_id == org_id)
            .order_by(Subscription.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_subscription_by_reference(
        session: AsyncSession, reference: str
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.provider_reference == reference
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_subscription(
        session: AsyncSession,
        org_id: uuid.UUID,
        *,
        provider: str,
        plan: str,
        status: str = "initiated",
        provider_reference: str | None = None,
        provider_customer_id: str | None = None,
    ) -> Subscription:
        sub = Subscription(
            organization_id=org_id,
            provider=provider,
            plan=plan,
            status=status,
            provider_reference=provider_reference,
            provider_customer_id=provider_customer_id,
        )
        session.add(sub)
        await session.flush()
        return sub

    @staticmethod
    async def update_subscription(
        session: AsyncSession,
        sub: Subscription,
        **kwargs: Any,
    ) -> Subscription:
        for key, value in kwargs.items():
            setattr(sub, key, value)
        sub.updated_at = datetime.now(timezone.utc)
        session.add(sub)
        await session.flush()
        return sub
