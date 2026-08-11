"""Plan entitlement policy and future Stripe integration boundary."""

from __future__ import annotations

from app.modules.billing.constants import PLAN_FEATURES
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import PlanEntitlements
from app.modules.organizations.constants import Plan


class BillingService:
    def __init__(self, repository: BillingRepository) -> None:
        self.repository = repository

    def entitlements(self, plan: Plan) -> PlanEntitlements:
        return PlanEntitlements(plan=plan, features=sorted(PLAN_FEATURES[plan]))

    def supports(self, plan: Plan, feature: str) -> bool:
        return feature in PLAN_FEATURES[plan]
