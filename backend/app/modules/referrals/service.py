from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import (
    ForbiddenException,
    ResourceNotFoundException,
    ValidationException,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.referrals.repository import (
    OrgPlanOverrideRepository,
    ReferralCodeRepository,
    ReferralRepository,
    ReferralRewardRepository,
)
from app.modules.referrals.schemas import (
    ClaimRewardResponse,
    ReferralInfoResponse,
    ReferralLeaderboardEntry,
)
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

# Default referral reward configuration
REFERRAL_REWARD_TYPE = "extra_dependencies"
REFERRAL_REWARD_VALUE = 5
REFERRAL_REWARD_DURATION_DAYS = 30

# Character set for the random portion of referral codes
_CODE_CHARS = string.ascii_uppercase + string.digits


def _generate_code_fragment(length: int = 4) -> str:
    """Generate a random alphanumeric code fragment."""
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(length))


def _build_referral_code(full_name: str) -> str:
    """Build a referral code: FIRST 4 CHARS of uppercase name + '-' + 4 random chars.

    Example: "Alexander Kof" -> "ALEX-7X2K"
    Strips whitespace and non-alpha chars from the name portion.
    """
    cleaned = "".join(c for c in full_name if c.isalpha()).upper()
    prefix = cleaned[:4] if len(cleaned) >= 4 else cleaned.ljust(4, "X")
    suffix = _generate_code_fragment(4)
    return f"{prefix}-{suffix}"


class ReferralService:
    def __init__(
        self,
        code_repo: ReferralCodeRepository = ReferralCodeRepository(),
        referral_repo: ReferralRepository = ReferralRepository(),
        reward_repo: ReferralRewardRepository = ReferralRewardRepository(),
        override_repo: OrgPlanOverrideRepository = OrgPlanOverrideRepository(),
    ) -> None:
        self.code_repo = code_repo
        self.referral_repo = referral_repo
        self.reward_repo = reward_repo
        self.override_repo = override_repo

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_referral_info(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> ReferralInfoResponse:
        """Get or create a referral code for the user and return full referral info."""
        user = await UserRepository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")

        # Get or create referral code
        ref_code_obj = await self.code_repo.get_by_user_id(session, user_id)
        if not ref_code_obj:
            code = await self._generate_unique_code(session, user.full_name)
            ref_code_obj = await self.code_repo.create(session, user_id, code)

        # Build referral link
        frontend_base = settings.FRONTEND_BASE_URL.rstrip("/")
        referral_link = f"{frontend_base}/ref/{ref_code_obj.code}"

        # Count referrals
        counts = await self.referral_repo.count_by_referrer(session, user_id)

        # Determine referral tier
        referral_tier = "standard"
        is_founding_referrer = False
        if counts["total"] >= 10:
            referral_tier = "founding"
            is_founding_referrer = True

        # Get rewards for this user
        all_rewards = await self.reward_repo.list_by_user(session, user_id)
        referrals = await self.referral_repo.list_by_referrer(session, user_id)
        referral_map = {r.id: r for r in referrals}

        pending_rewards = []
        earned_rewards = []
        for reward in all_rewards:
            ref = referral_map.get(reward.referral_id)
            reward_dict = {
                "id": str(reward.id),
                "type": reward.type,
                "value": reward.value,
                "status": reward.status,
                "expires_at": reward.expires_at.isoformat() if reward.expires_at else None,
            }
            if reward.status in ("pending", "active"):
                pending_rewards.append(reward_dict)
            if reward.status == "claimed":
                earned_rewards.append(reward_dict)

        return ReferralInfoResponse(
            referral_code=ref_code_obj.code,
            referral_link=referral_link,
            total_referrals=counts["total"],
            active_referrals=counts["active"],
            pending_rewards=pending_rewards,
            earned_rewards=earned_rewards,
            referral_tier=referral_tier,
            is_founding_referrer=is_founding_referrer,
        )

    async def claim_reward(
        self, session: AsyncSession, user_id: uuid.UUID, reward_id: uuid.UUID
    ) -> ClaimRewardResponse:
        """Claim a pending reward for the authenticated user."""
        reward = await self.reward_repo.get_by_id(session, reward_id)
        if not reward:
            raise ResourceNotFoundException("Reward not found")
        if reward.beneficiary_user_id != user_id:
            raise ForbiddenException("This reward does not belong to you")
        if reward.status != "pending":
            raise ValidationException(
                f"Reward is already '{reward.status}' and cannot be claimed"
            )

        # Check expiry
        if reward.expires_at and reward.expires_at < datetime.now(timezone.utc):
            raise ValidationException("This reward has expired")

        # Verify the referred user is active (logged in within 30 days)
        referral = await self.referral_repo.get_by_id(session, reward.referral_id)
        if not referral:
            raise ResourceNotFoundException("Associated referral not found")

        referred_user = await UserRepository.get_by_id(session, referral.referred_id)
        if not referred_user:
            raise ResourceNotFoundException("Referred user not found")

        # Check if referred user has been active (updated_at within 30 days = recent activity)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        if referred_user.updated_at < thirty_days_ago:
            raise ValidationException(
                "Reward cannot be claimed yet: the referred user must be active "
                "(logged in within the last 30 days)"
            )

        # Check if referred user has completed onboarding (created at least one dependency)
        from app.modules.dependencies.repository import DependencyRepository

        dep_count = await DependencyRepository.count_for_org(session, referral.referred_org_id) if referral.referred_org_id else 0
        if dep_count == 0:
            raise ValidationException(
                "Reward cannot be claimed yet: the referred user must add at least "
                "one dependency to complete onboarding"
            )

        # Activate the referral itself
        if referral.status == "pending":
            await self.referral_repo.update_status(session, referral, "active")

        # Apply the reward based on type
        expires_at = None
        if reward.type == "extra_dependencies":
            org_id = reward.beneficiary_org_id
            if not org_id:
                # Get user's org
                orgs = await OrganizationRepository.list_for_user(session, user_id)
                if orgs:
                    org_id = orgs[0].id
            if org_id:
                expires_at = datetime.now(timezone.utc) + timedelta(days=REFERRAL_REWARD_DURATION_DAYS)
                await self.override_repo.create(
                    session=session,
                    org_id=org_id,
                    override_type="extra_dependencies",
                    override_value=reward.value,
                    source="referral",
                    source_referral_id=reward.referral_id,
                    expires_at=expires_at,
                )
        elif reward.type == "discount_pct":
            org_id = reward.beneficiary_org_id
            if not org_id:
                orgs = await OrganizationRepository.list_for_user(session, user_id)
                if orgs:
                    org_id = orgs[0].id
            if org_id:
                expires_at = datetime.now(timezone.utc) + timedelta(days=REFERRAL_REWARD_DURATION_DAYS)
                await self.override_repo.create(
                    session=session,
                    org_id=org_id,
                    override_type="discount_pct",
                    override_value=reward.value,
                    source="referral",
                    source_referral_id=reward.referral_id,
                    expires_at=expires_at,
                )
        elif reward.type == "free_days":
            org_id = reward.beneficiary_org_id
            if not org_id:
                orgs = await OrganizationRepository.list_for_user(session, user_id)
                if orgs:
                    org_id = orgs[0].id
            if org_id:
                from app.modules.billing.repository import BillingRepository

                subscription = await BillingRepository.get_subscription(session, org_id)
                if subscription and subscription.current_period_end:
                    new_end = subscription.current_period_end + timedelta(days=reward.value)
                    await BillingRepository.update_subscription(
                        session, subscription, current_period_end=new_end
                    )
                expires_at = datetime.now(timezone.utc) + timedelta(days=90)

        # Activate and claim the reward
        await self.reward_repo.activate(session, reward)
        await self.reward_repo.claim(session, reward)

        await AuditLogService.log_event(
            session=session,
            event_type="referral_reward_claimed",
            user_id=user_id,
            resource_type="referral_reward",
            resource_id=str(reward_id),
            payload={
                "reward_type": reward.type,
                "reward_value": reward.value,
                "referral_id": str(reward.referral_id),
            },
        )

        return ClaimRewardResponse(
            message=f"Reward claimed! {reward.value} {reward.type.replace('_', ' ')} applied to your organization.",
            expires_at=expires_at,
        )

    async def get_leaderboard(
        self,
        session: AsyncSession,
        period: str = "all_time",
        page: int = 1,
        page_size: int = 20,
        current_user_id: uuid.UUID | None = None,
    ) -> tuple[list[ReferralLeaderboardEntry], int]:
        """Get the referral leaderboard."""
        valid_periods = {"all_time", "weekly", "monthly"}
        if period not in valid_periods:
            raise ValidationException(
                f"Invalid period '{period}'. Must be one of: {', '.join(sorted(valid_periods))}"
            )

        offset = (page - 1) * page_size
        entries_raw, total = await self.referral_repo.get_leaderboard(
            session, period=period, offset=offset, limit=page_size
        )

        entries: list[ReferralLeaderboardEntry] = []
        for idx, raw in enumerate(entries_raw):
            rank = offset + idx + 1
            referrer_id = raw["referrer_id"]
            is_self = current_user_id is not None and referrer_id == current_user_id

            user = await UserRepository.get_by_id(session, referrer_id)
            display_name = self._mask_display_name(user.full_name) if user and not is_self else (user.full_name if user else "Unknown")

            # Only show referral_code for self
            ref_code_obj = None
            if is_self:
                ref_code_obj = await self.code_repo.get_by_user_id(session, referrer_id)

            entries.append(
                ReferralLeaderboardEntry(
                    rank=rank,
                    user_id=referrer_id,
                    display_name=display_name,
                    referral_code=ref_code_obj.code if ref_code_obj else None,
                    total_referrals=raw["total_referrals"],
                    active_referrals=raw["active_referrals"],
                    is_self=is_self,
                )
            )

        return entries, total

    async def process_referral_on_register(
        self,
        session: AsyncSession,
        ref_code: str,
        new_user_id: uuid.UUID,
        new_user_email: str,
        new_user_org_id: uuid.UUID | None,
    ) -> None:
        """Process a referral code after a new user registers.

        This is the core referral logic called from auth service after registration.
        Creates the Referral record and two ReferralReward records (one for
        referrer, one for referred user).
        """
        if not ref_code:
            return

        # Look up the referral code
        code_obj = await self.code_repo.get_by_code(session, ref_code)
        if not code_obj:
            logger.warning("Registration with invalid referral code: %s", ref_code)
            return

        referrer_id = code_obj.user_id

        # Fraud prevention: cannot refer yourself
        if referrer_id == new_user_id:
            logger.warning("User %s attempted to use own referral code", new_user_id)
            return

        # Fraud prevention: check for duplicate referred email
        existing_referral = await self.referral_repo.get_by_referred_email(session, new_user_email)
        if existing_referral:
            logger.warning(
                "Duplicate referral email detected: %s already referred by %s",
                new_user_email,
                existing_referral.referrer_id,
            )
            return

        # Determine referral tier
        referrer_counts = await self.referral_repo.count_by_referrer(session, referrer_id)
        referral_tier = "founding" if referrer_counts["total"] >= 10 else "standard"

        # Create the Referral record
        referral = await self.referral_repo.create(
            session=session,
            referrer_id=referrer_id,
            referred_id=new_user_id,
            referral_code=code_obj.code,
            referred_email=new_user_email,
            referred_org_id=new_user_org_id,
            referral_tier=referral_tier,
        )

        # Calculate reward expiry (30 days from now)
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFERRAL_REWARD_DURATION_DAYS)

        # Create reward for the REFERRER
        await self.reward_repo.create(
            session=session,
            referral_id=referral.id,
            beneficiary_user_id=referrer_id,
            reward_type=REFERRAL_REWARD_TYPE,
            value=REFERRAL_REWARD_VALUE,
            beneficiary_org_id=None,  # Will be resolved at claim time
            expires_at=expires_at,
        )

        # Create reward for the REFERRED user
        await self.reward_repo.create(
            session=session,
            referral_id=referral.id,
            beneficiary_user_id=new_user_id,
            reward_type=REFERRAL_REWARD_TYPE,
            value=REFERRAL_REWARD_VALUE,
            beneficiary_org_id=new_user_org_id,
            expires_at=expires_at,
        )

        # Log lead capture event
        await AuditLogService.log_event(
            session=session,
            event_type="referral_lead_captured",
            user_id=referrer_id,
            org_id=new_user_org_id,
            resource_type="referral",
            resource_id=str(referral.id),
            payload={
                "referral_code": code_obj.code,
                "referred_email": new_user_email,
                "referred_user_id": str(new_user_id),
                "referral_tier": referral_tier,
            },
        )

        logger.info(
            "Referral processed: referrer=%s, referred=%s (%s), tier=%s",
            referrer_id,
            new_user_id,
            new_user_email,
            referral_tier,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_unique_code(
        self, session: AsyncSession, full_name: str
    ) -> str:
        """Generate a unique referral code, retrying on collision."""
        for _ in range(10):
            code = _build_referral_code(full_name)
            if not await self.code_repo.code_exists(session, code):
                return code
        # Fallback: use a longer random suffix
        prefix = "".join(c for c in full_name if c.isalpha()).upper()[:4].ljust(4, "X")
        return f"{prefix}-{_generate_code_fragment(8)}"

    @staticmethod
    def _mask_display_name(full_name: str) -> str:
        """Mask display name for leaderboard: 'Alexander Kof' -> 'Alex K.'"""
        parts = full_name.strip().split()
        if not parts:
            return "Anonymous"
        first = parts[0]
        masked_first = first[:4] if len(first) >= 4 else first
        if len(parts) > 1:
            last = parts[-1]
            return f"{masked_first} {last[0].upper()}."
        return f"{masked_first}."


referral_service = ReferralService()
