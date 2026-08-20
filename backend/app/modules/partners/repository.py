"""Data access for the Partner Referral program (v1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.partners.models import (
    PartnerCommission,
    PartnerPayout,
    PartnerProfile,
    PartnerReferral,
)


class PartnerProfileRepository:
    @staticmethod
    async def get_by_user_id(
        session: AsyncSession, user_id: uuid.UUID
    ) -> PartnerProfile | None:
        result = await session.execute(
            select(PartnerProfile).where(PartnerProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> PartnerProfile | None:
        result = await session.execute(
            select(PartnerProfile).where(PartnerProfile.id == partner_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: uuid.UUID,
        referral_code_id: uuid.UUID | None,
    ) -> PartnerProfile:
        profile = PartnerProfile(user_id=user_id, referral_code_id=referral_code_id)
        session.add(profile)
        await session.flush()
        return profile

    @staticmethod
    async def update(
        session: AsyncSession, profile: PartnerProfile, **kwargs
    ) -> PartnerProfile:
        for key, value in kwargs.items():
            if value is not None and hasattr(profile, key):
                setattr(profile, key, value)
        session.add(profile)
        await session.flush()
        return profile

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        status: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerProfile], int]:
        base = select(PartnerProfile)
        count_q = select(func.count()).select_from(PartnerProfile)
        if status:
            base = base.where(PartnerProfile.status == status)
            count_q = count_q.where(PartnerProfile.status == status)
        if search:
            # join users to search by email
            from app.modules.users.models import User

            base = base.join(User, User.id == PartnerProfile.user_id).where(
                User.email.ilike(f"%{search}%")
            )
            count_q = count_q.join(User, User.id == PartnerProfile.user_id).where(
                User.email.ilike(f"%{search}%")
            )
        total = (await session.execute(count_q)).scalar() or 0
        rows = await session.execute(
            base.order_by(PartnerProfile.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), int(total)


class PartnerReferralRepository:
    @staticmethod
    async def get_by_referred_user(
        session: AsyncSession, referred_user_id: uuid.UUID
    ) -> PartnerReferral | None:
        result = await session.execute(
            select(PartnerReferral).where(
                PartnerReferral.referred_user_id == referred_user_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, referral_id: uuid.UUID
    ) -> PartnerReferral | None:
        result = await session.execute(
            select(PartnerReferral).where(PartnerReferral.id == referral_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        partner_id: uuid.UUID,
        referred_user_id: uuid.UUID,
        referred_org_id: uuid.UUID | None,
        status: str = "signed_up",
    ) -> PartnerReferral:
        referral = PartnerReferral(
            partner_id=partner_id,
            referred_user_id=referred_user_id,
            referred_org_id=referred_org_id,
            status=status,
        )
        session.add(referral)
        await session.flush()
        return referral

    @staticmethod
    async def update(
        session: AsyncSession, referral: PartnerReferral, **kwargs
    ) -> PartnerReferral:
        for key, value in kwargs.items():
            if value is not None and hasattr(referral, key):
                setattr(referral, key, value)
        session.add(referral)
        await session.flush()
        return referral

    @staticmethod
    async def count_by_partner(
        session: AsyncSession, partner_id: uuid.UUID, status: str | None = None
    ) -> int:
        q = select(func.count()).select_from(PartnerReferral).where(
            PartnerReferral.partner_id == partner_id
        )
        if status:
            q = q.where(PartnerReferral.status == status)
        return int((await session.execute(q)).scalar() or 0)

    @staticmethod
    async def list_by_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerReferral], int]:
        count_q = (
            select(func.count())
            .select_from(PartnerReferral)
            .where(PartnerReferral.partner_id == partner_id)
        )
        total = int((await session.execute(count_q)).scalar() or 0)
        rows = await session.execute(
            select(PartnerReferral)
            .where(PartnerReferral.partner_id == partner_id)
            .order_by(PartnerReferral.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total


class PartnerCommissionRepository:
    @staticmethod
    async def get_by_billing_event(
        session: AsyncSession, billing_event_id: str, partner_id: uuid.UUID
    ) -> PartnerCommission | None:
        result = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.billing_event_id == billing_event_id,
                PartnerCommission.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, commission_id: uuid.UUID
    ) -> PartnerCommission | None:
        result = await session.execute(
            select(PartnerCommission).where(PartnerCommission.id == commission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        referral_id: uuid.UUID | None,
        billing_event_id: str,
        period: str,
        subscription_amount_minor: int,
        commission_amount_minor: int,
        currency: str,
        rate: int,
        payable_at: datetime | None = None,
    ) -> PartnerCommission:
        commission = PartnerCommission(
            partner_id=partner_id,
            referral_id=referral_id,
            billing_event_id=billing_event_id,
            period=period,
            subscription_amount_minor=subscription_amount_minor,
            commission_amount_minor=commission_amount_minor,
            currency=currency,
            rate=rate,
            status="pending",
            payable_at=payable_at,
        )
        session.add(commission)
        await session.flush()
        return commission

    @staticmethod
    async def update(
        session: AsyncSession, commission: PartnerCommission, **kwargs
    ) -> PartnerCommission:
        for key, value in kwargs.items():
            if value is not None and hasattr(commission, key):
                setattr(commission, key, value)
        session.add(commission)
        await session.flush()
        return commission

    @staticmethod
    async def list_by_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerCommission], int]:
        count_q = (
            select(func.count())
            .select_from(PartnerCommission)
            .where(PartnerCommission.partner_id == partner_id)
        )
        total = int((await session.execute(count_q)).scalar() or 0)
        rows = await session.execute(
            select(PartnerCommission)
            .where(PartnerCommission.partner_id == partner_id)
            .order_by(PartnerCommission.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID | None = None,
        status: str | None = None,
        period: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerCommission], int]:
        conditions = []
        if partner_id:
            conditions.append(PartnerCommission.partner_id == partner_id)
        if status:
            conditions.append(PartnerCommission.status == status)
        if period:
            conditions.append(PartnerCommission.period == period)
        count_q = select(func.count()).select_from(PartnerCommission)
        base = select(PartnerCommission)
        for cond in conditions:
            count_q = count_q.where(cond)
            base = base.where(cond)
        total = int((await session.execute(count_q)).scalar() or 0)
        rows = await session.execute(
            base.order_by(PartnerCommission.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    @staticmethod
    async def sum_amount_by_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        statuses: list[str],
        exclude_reversed: bool = True,
        exclude_reserved: bool = False,
        period: str | None = None,
    ) -> int:
        q = (
            select(func.coalesce(func.sum(PartnerCommission.commission_amount_minor), 0))
            .where(PartnerCommission.partner_id == partner_id)
        )
        if statuses:
            q = q.where(PartnerCommission.status.in_(statuses))
        if exclude_reversed:
            q = q.where(PartnerCommission.status != "reversed")
        if exclude_reserved:
            q = q.where(PartnerCommission.payout_id.is_(None))
        if period:
            q = q.where(PartnerCommission.period == period)
        return int((await session.execute(q)).scalar() or 0)

    @staticmethod
    async def payable_by_partner(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> list[PartnerCommission]:
        rows = await session.execute(
            select(PartnerCommission)
            .where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.status == "payable",
                PartnerCommission.payout_id.is_(None),
            )
            .order_by(PartnerCommission.created_at.asc())
        )
        return list(rows.scalars().all())

    @staticmethod
    async def pending_past_hold(
        session: AsyncSession, now: datetime | None = None
    ) -> list[PartnerCommission]:
        now = now or datetime.now(timezone.utc)
        rows = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.status == "pending",
                PartnerCommission.payable_at.is_not(None),
                PartnerCommission.payable_at <= now,
            )
        )
        return list(rows.scalars().all())

    @staticmethod
    async def commissions_for_payout(
        session: AsyncSession, payout_id: uuid.UUID
    ) -> list[PartnerCommission]:
        rows = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.payout_id == payout_id
            )
        )
        return list(rows.scalars().all())


class PartnerPayoutRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        partner_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        period: str | None = None,
    ) -> PartnerPayout:
        payout = PartnerPayout(
            partner_id=partner_id,
            amount_minor=amount_minor,
            currency=currency,
            period=period,
            status="pending",
        )
        session.add(payout)
        await session.flush()
        return payout

    @staticmethod
    async def get_by_id(
        session: AsyncSession, payout_id: uuid.UUID
    ) -> PartnerPayout | None:
        result = await session.execute(
            select(PartnerPayout).where(PartnerPayout.id == payout_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        session: AsyncSession, payout: PartnerPayout, **kwargs
    ) -> PartnerPayout:
        for key, value in kwargs.items():
            if value is not None and hasattr(payout, key):
                setattr(payout, key, value)
        session.add(payout)
        await session.flush()
        return payout

    @staticmethod
    async def list_by_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerPayout], int]:
        count_q = (
            select(func.count())
            .select_from(PartnerPayout)
            .where(PartnerPayout.partner_id == partner_id)
        )
        total = int((await session.execute(count_q)).scalar() or 0)
        rows = await session.execute(
            select(PartnerPayout)
            .where(PartnerPayout.partner_id == partner_id)
            .order_by(PartnerPayout.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        status: str | None = None,
        partner_id: uuid.UUID | None = None,
        period: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PartnerPayout], int]:
        conditions = []
        if status:
            conditions.append(PartnerPayout.status == status)
        if partner_id:
            conditions.append(PartnerPayout.partner_id == partner_id)
        if period:
            conditions.append(PartnerPayout.period == period)
        count_q = select(func.count()).select_from(PartnerPayout)
        base = select(PartnerPayout)
        for cond in conditions:
            count_q = count_q.where(cond)
            base = base.where(cond)
        total = int((await session.execute(count_q)).scalar() or 0)
        rows = await session.execute(
            base.order_by(PartnerPayout.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total
