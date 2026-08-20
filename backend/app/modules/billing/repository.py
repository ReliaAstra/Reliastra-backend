import uuid
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
    async def get_subscription(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Subscription | None:
        result = await session.execute(
            select(Subscription).where(Subscription.organization_id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_subscription(
        session: AsyncSession,
        org_id: uuid.UUID,
        provider: str = "paystack",
        provider_customer_id: str | None = None,
        provider_subscription_id: str | None = None,
        plan: str = "free",
        status: str = "inactive",
        **periods: Any,
    ) -> Subscription:
        subscription = Subscription(
            organization_id=org_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            provider_subscription_id=provider_subscription_id,
            plan=plan,
            status=status,
            current_period_start=periods.get("current_period_start"),
            current_period_end=periods.get("current_period_end"),
        )
        session.add(subscription)
        await session.flush()
        return subscription

    @staticmethod
    async def update_subscription(
        session: AsyncSession, subscription: Subscription, **kwargs: Any
    ) -> Subscription:
        for key, value in kwargs.items():
            if value is not None and hasattr(subscription, key):
                setattr(subscription, key, value)
        session.add(subscription)
        await session.flush()
        return subscription

    @staticmethod
    async def get_org_by_provider_customer(
        session: AsyncSession,
        customer_id: str,
        provider: str = "paystack",
    ) -> Organization | None:
        result = await session.execute(
            select(Organization)
            .join(
                Subscription,
                Subscription.organization_id == Organization.id,
            )
            .where(
                Subscription.provider_customer_id == customer_id,
                Subscription.provider == provider,
            )
        )
        return result.scalar_one_or_none()
