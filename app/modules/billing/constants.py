from app.core.permissions import PLAN_CHECK_INTERVALS, PLAN_DEPENDENCY_LIMITS, Plan

# Monthly plan prices expressed in kobo (NGN * 100), the unit Paystack expects.
PLAN_PRICES_KOBO: dict[str, int] = {
    Plan.FREE.value: 0,
    Plan.STANDARD.value: 200000,     # NGN 2,000
    Plan.PROFESSIONAL.value: 600000,  # NGN 6,000
    Plan.AGENCY.value: 1500000,       # NGN 15,000
}

# Webhook events we care about (provider-agnostic event type string).
SUBSCRIPTION_EVENTS = {"subscription.create", "subscription.update", "subscription.disable"}
PAYMENT_SUCCESS_EVENTS = {"charge.success", "invoice.payment_succeeded"}

__all__ = [
    "PLAN_CHECK_INTERVALS",
    "PLAN_DEPENDENCY_LIMITS",
    "PLAN_PRICES_KOBO",
    "SUBSCRIPTION_EVENTS",
    "PAYMENT_SUCCESS_EVENTS",
    "Plan",
]
