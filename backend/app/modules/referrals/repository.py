from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referrals.models import (
    OrgPlanOverride,
    Referral,
    ReferralCode,
    ReferralReward,
)


class ReferralCodeRepository:
    @staticmethod
    async def get_by_user_id(
        session: AsyncSession, user_id: uuid.UUID
    ) -> ReferralCode | None:
        result = await session.execute(
            select(ReferralCode).where(ReferralCode.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        session: AsyncSession, code: str
    ) -> ReferralCode | None:
        result = await session.execute(
            select(ReferralCode).where(
                ReferralCode.code == code.upper(),
                ReferralCode.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession, user_id: uuid.UUID, code: str
    ) -> ReferralCode:
        referral_code = ReferralCode(user_id=user_id, code=code)
        session.add(referral_code)
        await session.flush()
        return referral_code

    @staticmethod
    async def code_exists(session: AsyncSession, code: str) -> bool:
        result = await session.execute(
            select(func.count())
            .select_from(ReferralCode)
            .where(ReferralCode.code == code.upper())
        )
        return (result.scalar() or 0) > 0


class ReferralRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        referrer_id: uuid.UUID,
        referred_id: uuid.UUID,
        referral_code: str,
        referred_email: str,
        referred_org_id: uuid.UUID | None = None,
        referral_tier: str = "standard",
    ) -> Referral:
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            referral_code=referral_code,
            referred_email=referred_email,
            referred_org_id=referred_org_id,
            referral_tier=referral_tier,
            status="pending",
        )
        session.add(referral)
        await session.flush()
        return referral

    @staticmethod
    async def get_by_id(
        session: AsyncSession, referral_id: uuid.UUID
    ) -> Referral | None:
        result = await session.execute(
            select(Referral).where(Referral.id == referral_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_referrer_and_referred(
        session: AsyncSession, referrer_id: uuid.UUID, referred_id: uuid.UUID
    ) -> Referral | None:
        result = await session.execute(
            select(Referral).where(
                Referral.referrer_id == referrer_id,
                Referral.referred_id == referred_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_referred_email(
        session: AsyncSession, email: str
    ) -> Referral | None:
        result = await session.execute(
            select(Referral).where(Referral.referred_email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_referrer(
        session: AsyncSession, referrer_id: uuid.UUID
    ) -> list[Referral]:
        result = await session.execute(
            select(Referral)
            .where(Referral.referrer_id == referrer_id)
            .order_by(Referral.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_by_referrer(
        session: AsyncSession, referrer_id: uuid.UUID
    ) -> dict[str, int]:
        total_result = await session.execute(
            select(func.count())
            .select_from(Referral)
            .where(Referral.referrer_id == referrer_id)
        )
        active_result = await session.execute(
            select(func.count())
            .select_from(Referral)
            .where(
                Referral.referrer_id == referrer_id,
                Referral.status == "active",
            )
        )
        return {
            "total": total_result.scalar() or 0,
            "active": active_result.scalar() or 0,
        }

    @staticmethod
    async def update_status(
        session: AsyncSession, referral: Referral, status: str
    ) -> Referral:
        referral.status = status
        if status == "active":
            referral.activated_at = datetime.now(timezone.utc)
        session.add(referral)
        await session.flush()
        return referral

    @staticmethod
    async def get_leaderboard(
        session: AsyncSession,
        period: str = "all_time",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return ranked referrers with total/active counts."""
        base_query = (
            select(
                Referral.referrer_id,
                func.count().label("total_referrals"),
                func.sum(
                    func.cast(Referral.status == "active", Integer)  # type: ignore[arg-type]
                ).label("active_referrals"),
            )
            .group_by(Referral.referrer_id)
        )

        if period == "monthly":
            cutoff = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            base_query = base_query.where(Referral.created_at >= cutoff)
        elif period == "weekly":
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(weeks=1)
            base_query = base_query.where(Referral.created_at >= cutoff)

        # Total count
        count_q = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Ranked results
        ranked = (
            base_query
            .order_by(func.count().desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(ranked)
        rows = result.all()
        entries = [
            {
                "referrer_id": row.referrer_id,
                "total_referrals": row.total_referrals,
                "active_referrals": int(row.active_referrals or 0),
            }
            for row in rows
        ]
        return entries, total


class ReferralRewardRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        referral_id: uuid.UUID,
        beneficiary_user_id: uuid.UUID,
        reward_type: str,
        value: int,
        beneficiary_org_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> ReferralReward:
        reward = ReferralReward(
            referral_id=referral_id,
            beneficiary_user_id=beneficiary_user_id,
            beneficiary_org_id=beneficiary_org_id,
            type=reward_type,
            value=value,
            status="pending",
            expires_at=expires_at,
        )
        session.add(reward)
        await session.flush()
        return reward

    @staticmethod
    async def get_by_id(
        session: AsyncSession, reward_id: uuid.UUID
    ) -> ReferralReward | None:
        result = await session.execute(
            select(ReferralReward).where(ReferralReward.id == reward_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> list[ReferralReward]:
        result = await session.execute(
            select(ReferralReward)
            .where(ReferralReward.beneficiary_user_id == user_id)
            .order_by(ReferralReward.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_referral(
        session: AsyncSession, referral_id: uuid.UUID
    ) -> list[ReferralReward]:
        result = await session.execute(
            select(ReferralReward)
            .where(ReferralReward.referral_id == referral_id)
            .order_by(ReferralReward.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def activate(
        session: AsyncSession, reward: ReferralReward
    ) -> ReferralReward:
        reward.status = "active"
        reward.activated_at = datetime.now(timezone.utc)
        session.add(reward)
        await session.flush()
        return reward

    @staticmethod
    async def claim(
        session: AsyncSession, reward: ReferralReward
    ) -> ReferralReward:
        reward.status = "claimed"
        reward.claimed_at = datetime.now(timezone.utc)
        session.add(reward)
        await session.flush()
        return reward


class OrgPlanOverrideRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        override_type: str,
        override_value: int,
        source: str,
        source_referral_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> OrgPlanOverride:
        override = OrgPlanOverride(
            org_id=org_id,
            override_type=override_type,
            override_value=override_value,
            source=source,
            source_referral_id=source_referral_id,
            is_active=True,
            expires_at=expires_at,
        )
        session.add(override)
        await session.flush()
        return override

    @staticmethod
    async def list_active_by_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[OrgPlanOverride]:
        result = await session.execute(
            select(OrgPlanOverride).where(
                OrgPlanOverride.org_id == org_id,
                OrgPlanOverride.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_org_and_type(
        session: AsyncSession, org_id: uuid.UUID, override_type: str
    ) -> OrgPlanOverride | None:
        result = await session.execute(
            select(OrgPlanOverride).where(
                OrgPlanOverride.org_id == org_id,
                OrgPlanOverride.override_type == override_type,
                OrgPlanOverride.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def deactivate(
        session: AsyncSession, override: OrgPlanOverride
    ) -> OrgPlanOverride:
        override.is_active = False
        session.add(override)
        await session.flush()
        return override
