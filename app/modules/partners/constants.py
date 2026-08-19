"""Domain constants for the RELIASTRA Partner Referral program (v1).

Everything money-related is expressed in integer minor units with an
explicit ISO-4217 currency code. Rates are integer percentages.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class PartnerStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"


#: Statuses in which a partner may accrue new commissions / referrals.
EARNING_STATUSES: frozenset[str] = frozenset({PartnerStatus.ACTIVE.value})


class ReferralStatus(StrEnum):
    REFERRED = "referred"
    SIGNED_UP = "signed_up"
    PAID = "paid"
    CHURNED = "churned"


class CommissionStatus(StrEnum):
    PENDING = "pending"
    PAYABLE = "payable"
    PAID = "paid"
    REVERSED = "reversed"


class PayoutStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


#: Reversal reasons recorded on the commission ledger.
class ReversalReason(StrEnum):
    REFUND = "refund"
    CHARGEBACK = "chargeback"
    ADMIN = "admin"
