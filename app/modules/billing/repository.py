import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository


class BillingRepository:
    @staticmethod
    async def get_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Organization | None:
        return await OrganizationRepository.get_by_id(session, org_id)

    @staticmethod
    async def get_org_by_stripe_customer(
        session: AsyncSession, customer_id: str
    ) -> Organization | None:
        """Look up an organization by its Stripe customer ID."""
        query = select(Organization).where(
            Organization.stripe_customer_id == customer_id
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_org_plan(
        session: AsyncSession,
        org: Organization,
        plan: str,
        customer_id: str | None = None,
        subscription_id: str | None = None,
    ) -> Organization:
        kwargs = {"plan": plan}
        if customer_id is not None:
            kwargs["stripe_customer_id"] = customer_id
        if subscription_id is not None:
            kwargs["stripe_subscription_id"] = subscription_id
        return await OrganizationRepository.update(session, org, **kwargs)
