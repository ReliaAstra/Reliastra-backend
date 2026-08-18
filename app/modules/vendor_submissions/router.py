from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import OffsetPagination
from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.dependencies import require_admin
from app.modules.users.models import User
from app.modules.vendor_submissions.schemas import (
    AdminActionResponse,
    ApproveVendorRequest,
    RejectVendorRequest,
    VendorSubmitRequest,
    VendorSubmitResponse,
    VendorSubmissionListResponse,
)
from app.modules.vendor_submissions.service import (
    VendorSubmissionService,
    vendor_submission_service,
)

# ---------------------------------------------------------------------------
# Rate limiters — dual rate limiting (IP + email)
# ---------------------------------------------------------------------------

# Per-IP: 10 submissions per minute
submission_ip_limiter = SlidingWindowRateLimiter(
    limit=10,
    window_seconds=60,
    key_prefix="rl_vendor_submit_ip",
)

# Per-email: 5 submissions per minute
submission_email_limiter = SlidingWindowRateLimiter(
    limit=5,
    window_seconds=60,
    key_prefix="rl_vendor_submit_email",
)

# ---------------------------------------------------------------------------
# Public submission router (no auth required)
# ---------------------------------------------------------------------------

submission_router = APIRouter(
    prefix="/v1/vendors",
    tags=["Vendor Submissions"],
)


def get_submission_service() -> VendorSubmissionService:
    return vendor_submission_service


async def _enforce_dual_rate_limit(request: Request, submitter_email: str) -> None:
    """Enforce both per-IP and per-email rate limits."""
    client = request.client
    ip = client.host if client else "unknown_ip"
    await enforce_rate_limit(request, submission_ip_limiter, identifier=ip)
    await enforce_rate_limit(request, submission_email_limiter, identifier=submitter_email)


@submission_router.post(
    "/submit",
    response_model=VendorSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new vendor for review",
    description=(
        "Public endpoint to submit a new SaaS vendor for monitoring. "
        "Rate-limited to 10 requests/min per IP and 5 requests/min per email."
    ),
)
async def submit_vendor(
    request: Request,
    body: VendorSubmitRequest,
    db: AsyncSession = Depends(get_db),
    service: VendorSubmissionService = Depends(get_submission_service),
) -> VendorSubmitResponse:
    # Dual rate limiting (IP + email)
    await _enforce_dual_rate_limit(request, str(body.submitter_email))

    return await service.submit_vendor(db, body)


# ---------------------------------------------------------------------------
# Admin router (auth required, admin+ role)
# ---------------------------------------------------------------------------

submission_admin_router = APIRouter(
    prefix="/v1/vendors/submissions",
    tags=["Vendor Submissions Admin"],
    dependencies=[Depends(require_admin)],
)


@submission_admin_router.get(
    "",
    response_model=OffsetPagination[VendorSubmissionListResponse],
    summary="List vendor submissions",
    description="List all vendor submissions with optional status filtering. Requires admin role.",
)
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
    submission_status: str | None = Query(
        default=None,
        alias="status",
        description="Filter by submission status (e.g. pending_review, approved, rejected)",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    service: VendorSubmissionService = Depends(get_submission_service),
) -> OffsetPagination[VendorSubmissionListResponse]:
    items, total = await service.list_submissions(
        db, status=submission_status, page=page, page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return OffsetPagination(
        items=items,
        total=total,
        page=page,
        size=page_size,
        pages=total_pages,
    )


@submission_admin_router.post(
    "/{submission_id}/approve",
    response_model=AdminActionResponse,
    summary="Approve a vendor submission",
    description="Approve a pending vendor submission and create the vendor. Requires admin role.",
)
async def approve_submission(
    submission_id: uuid.UUID,
    body: ApproveVendorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    service: VendorSubmissionService = Depends(get_submission_service),
) -> AdminActionResponse:
    return await service.approve_submission(
        db,
        submission_id=submission_id,
        admin_user_id=current_user.id,
        request=body,
    )


@submission_admin_router.post(
    "/{submission_id}/reject",
    response_model=AdminActionResponse,
    summary="Reject a vendor submission",
    description="Reject a pending vendor submission with a reason. Requires admin role.",
)
async def reject_submission(
    submission_id: uuid.UUID,
    body: RejectVendorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    service: VendorSubmissionService = Depends(get_submission_service),
) -> AdminActionResponse:
    return await service.reject_submission(
        db,
        submission_id=submission_id,
        admin_user_id=current_user.id,
        request=body,
    )
