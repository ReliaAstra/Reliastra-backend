"""Billing router; Stripe HTTP endpoints are intentionally deferred for MVP."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1/billing", tags=["billing"])
