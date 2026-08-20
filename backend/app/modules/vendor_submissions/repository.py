from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vendor_submissions.models import (
    VendorSubmission,
    VendorSubmissionEndpoint,
)


async def create_submission(
    session: AsyncSession,
    **kwargs: object,
) -> VendorSubmission:
    """Create a new vendor submission record."""
    submission = VendorSubmission(**kwargs)
    session.add(submission)
    await session.flush()
    return submission


async def create_submission_endpoint(
    session: AsyncSession,
    **kwargs: object,
) -> VendorSubmissionEndpoint:
    """Create a new vendor submission endpoint record."""
    endpoint = VendorSubmissionEndpoint(**kwargs)
    session.add(endpoint)
    await session.flush()
    return endpoint


async def get_by_vendor_name(
    session: AsyncSession,
    vendor_name: str,
) -> VendorSubmission | None:
    """Look up a submission by its sanitized vendor_name."""
    result = await session.execute(
        select(VendorSubmission).where(
            VendorSubmission.vendor_name == vendor_name.lower()
        )
    )
    return result.scalar_one_or_none()


async def get_by_id(
    session: AsyncSession,
    submission_id: uuid.UUID,
) -> VendorSubmission | None:
    """Look up a submission by its UUID."""
    result = await session.execute(
        select(VendorSubmission).where(VendorSubmission.id == submission_id)
    )
    return result.scalar_one_or_none()


async def list_submissions(
    session: AsyncSession,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[VendorSubmission], int]:
    """Return a paginated list of submissions, optionally filtered by status."""
    base_query = select(VendorSubmission)
    count_query = select(func.count()).select_from(VendorSubmission)

    if status is not None:
        base_query = base_query.where(VendorSubmission.status == status)
        count_query = count_query.where(VendorSubmission.status == status)

    # Total count
    total_result = await session.execute(count_query)
    total: int = total_result.scalar() or 0

    # Paginated results
    offset = (page - 1) * page_size
    base_query = (
        base_query
        .order_by(VendorSubmission.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(base_query)
    submissions = list(result.scalars().all())
    return submissions, total


async def update_status(
    session: AsyncSession,
    submission_id: uuid.UUID,
    status: str,
    reviewed_by: uuid.UUID,
    review_note: str | None = None,
) -> VendorSubmission | None:
    """Update the status of a vendor submission."""
    submission = await get_by_id(session, submission_id)
    if submission is None:
        return None
    submission.status = status
    submission.reviewed_by = reviewed_by
    submission.reviewed_at = datetime.now(timezone.utc)
    if review_note is not None:
        submission.review_note = review_note
    session.add(submission)
    await session.flush()
    return submission
