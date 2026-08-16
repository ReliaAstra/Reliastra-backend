from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ResourceNotFoundException, ValidationException
from app.core.ssrf_protection import validate_outbound_url
from app.modules.vendor_submissions import repository as repo
from app.modules.vendor_submissions.schemas import (
    AdminActionResponse,
    ApproveVendorRequest,
    RejectVendorRequest,
    VendorSubmitRequest,
    VendorSubmitResponse,
    VendorSubmissionListResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vendor-name sanitisation
# ---------------------------------------------------------------------------

_SPECIAL_CHARS_RE = re.compile(r"[^a-z0-9-]+")


def _sanitize_vendor_name(raw: str) -> str:
    """Lower-case, strip, replace spaces/special chars with hyphens, collapse."""
    name = raw.strip().lower()
    name = re.sub(r"\s+", "-", name)
    name = _SPECIAL_CHARS_RE.sub("", name)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip("-")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VendorSubmissionService:
    """Manages the public vendor submission workflow and admin review."""

    async def submit_vendor(
        self,
        session: AsyncSession,
        request: VendorSubmitRequest,
        user_id: uuid.UUID | None = None,
    ) -> VendorSubmitResponse:
        """Process a public vendor submission request.

        Steps:
        1. Check for duplicates in the existing vendors table.
        2. Check for duplicates in submissions table.
        3. Validate the website URL via async HEAD request.
        4. Create the submission + endpoint records.
        5. Log a lead-capture event.
        6. Send a confirmation email to the submitter.
        """

        # 1. Sanitize & deduplicate against existing vendors
        vendor_name = _sanitize_vendor_name(request.vendor_name)
        if not vendor_name:
            raise ValidationException("vendor_name must contain alphanumeric characters")

        from app.modules.vendors.repository import VendorRepository
        existing_vendor = await VendorRepository.get_by_name(session, vendor_name)
        if existing_vendor:
            return VendorSubmitResponse(
                id=uuid.UUID(int=0),
                vendor_name=vendor_name,
                display_name=request.display_name,
                status="already_exists",
                message="This vendor is already tracked in Reliastra.",
                estimated_days=None,
            )

        # 2. Deduplicate against pending submissions
        existing_submission = await repo.get_by_vendor_name(session, vendor_name)
        if existing_submission and existing_submission.status == "pending_review":
            return VendorSubmitResponse(
                id=existing_submission.id,
                vendor_name=vendor_name,
                display_name=request.display_name,
                status="pending_review",
                message="This vendor has already been submitted and is awaiting review.",
                estimated_days=3,
            )

        # 3. Validate the website URL (HEAD request)
        if request.website_url:
            await self._validate_url(request.website_url)

        # 4. Build the endpoints data payload for JSON storage
        endpoints_data: list[dict] = []
        if request.endpoints:
            for ep in request.endpoints:
                await self._validate_url(str(ep.url))
                endpoints_data.append({
                    "name": ep.name,
                    "url": str(ep.url),
                    "method": ep.method,
                    "expected_status": ep.expected_status,
                })

        # 5. Create the submission record
        submission = await repo.create_submission(
            session,
            vendor_name=vendor_name,
            display_name=request.display_name,
            category=request.category,
            website_url=request.website_url,
            submitter_email=str(request.submitter_email),
            submitter_name=request.submitter_name,
            submitter_user_id=user_id,
            reason=request.reason,
            endpoints_data=endpoints_data if endpoints_data else None,
            status="pending_review",
        )

        # 6. Create submission endpoint records
        for ep_data in endpoints_data:
            await repo.create_submission_endpoint(
                session,
                submission_id=submission.id,
                name=ep_data["name"],
                url=ep_data["url"],
                method=ep_data["method"],
                expected_status=ep_data["expected_status"],
            )

        # 7. Log a lead-capture event (simple inline insert)
        await self._log_lead_capture(
            session,
            submission_id=submission.id,
            vendor_name=vendor_name,
            email=str(request.submitter_email),
            name=request.submitter_name,
        )

        # 8. Send confirmation email (fire-and-forget; failures logged, not raised)
        await self._send_confirmation_email(
            to_email=str(request.submitter_email),
            vendor_name=vendor_name,
            display_name=request.display_name,
        )

        return VendorSubmitResponse(
            id=submission.id,
            vendor_name=submission.vendor_name,
            display_name=submission.display_name,
            status=submission.status,
            message=(
                "Your vendor submission has been received and is pending review. "
                "We will notify you once it has been processed."
            ),
            estimated_days=3,
        )

    # ------------------------------------------------------------------
    # List (admin)
    # ------------------------------------------------------------------

    async def list_submissions(
        self,
        session: AsyncSession,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[VendorSubmissionListResponse], int]:
        submissions, total = await repo.list_submissions(
            session, status=status, page=page, page_size=page_size,
        )
        items = [
            VendorSubmissionListResponse.model_validate(s) for s in submissions
        ]
        return items, total

    # ------------------------------------------------------------------
    # Approve (admin)
    # ------------------------------------------------------------------

    async def approve_submission(
        self,
        session: AsyncSession,
        submission_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        request: ApproveVendorRequest,
    ) -> AdminActionResponse:
        submission = await repo.get_by_id(session, submission_id)
        if submission is None:
            raise ResourceNotFoundException("Vendor submission not found")

        if submission.status != "pending_review":
            raise ConflictException(
                f"Cannot approve a submission with status '{submission.status}'. "
                "Only 'pending_review' submissions may be approved."
            )

        # Create vendor in the vendors table
        from app.modules.vendors.repository import VendorRepository

        # Use the first approved endpoint or a reasonable default
        endpoint_urls = []
        if request.endpoints:
            for ep in request.endpoints:
                endpoint_urls.append(str(ep.url))
        primary_url = endpoint_urls[0] if endpoint_urls else (
            submission.website_url or "https://example.com"
        )
        category = request.category or submission.category or "uncategorized"

        # Check for duplicate vendor_name in the vendors table
        existing_vendor = await VendorRepository.get_by_name(
            session, request.vendor_name
        )
        if existing_vendor:
            raise ConflictException(
                f"A vendor with name '{request.vendor_name}' already exists."
            )

        new_vendor = await VendorRepository.create(
            session,
            vendor_name=request.vendor_name,
            display_name=request.display_name,
            endpoint_url=primary_url,
            category=category,
            is_public=True,
        )

        # Create additional vendor endpoints beyond the primary one
        for ep_url in endpoint_urls[1:]:
            await VendorRepository.create_vendor_endpoint(
                session, vendor_id=new_vendor.id, endpoint_url=ep_url,
            )

        # Update the submission status
        updated = await repo.update_status(
            session,
            submission_id=submission_id,
            status="approved",
            reviewed_by=admin_user_id,
            review_note=None,
        )

        # Send approval notification to the submitter
        await self._send_review_email(
            to_email=submission.submitter_email,
            vendor_name=submission.vendor_name,
            display_name=request.display_name,
            status="approved",
        )

        return AdminActionResponse(
            message=f"Vendor '{request.display_name}' has been approved and added.",
            submission_id=submission_id,
            status="approved",
        )

    # ------------------------------------------------------------------
    # Reject (admin)
    # ------------------------------------------------------------------

    async def reject_submission(
        self,
        session: AsyncSession,
        submission_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        request: RejectVendorRequest,
    ) -> AdminActionResponse:
        submission = await repo.get_by_id(session, submission_id)
        if submission is None:
            raise ResourceNotFoundException("Vendor submission not found")

        if submission.status != "pending_review":
            raise ConflictException(
                f"Cannot reject a submission with status '{submission.status}'. "
                "Only 'pending_review' submissions may be rejected."
            )

        updated = await repo.update_status(
            session,
            submission_id=submission_id,
            status="rejected",
            reviewed_by=admin_user_id,
            review_note=request.reason,
        )

        # Send rejection notification to the submitter
        await self._send_review_email(
            to_email=submission.submitter_email,
            vendor_name=submission.vendor_name,
            display_name=submission.display_name,
            status="rejected",
            reason=request.reason,
        )

        return AdminActionResponse(
            message=f"Vendor submission '{submission.vendor_name}' has been rejected.",
            submission_id=submission_id,
            status="rejected",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _validate_url(url: str) -> None:
        """Validate a URL is safe (SSRF check) and reachable (HEAD request)."""
        validate_outbound_url(url)

        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.head(url)
                # Accept any 2xx/3xx/4xx — just verify the server responds
                logger.debug("URL validation HEAD %s → %d", url, resp.status_code)
        except httpx.TimeoutException:
            logger.warning("URL validation timed out for %s", url)
            # Timeout is not fatal — the URL might still be valid
        except Exception as exc:
            logger.warning("URL validation failed for %s: %s", url, exc)
            # Fail open — network issues shouldn't block submissions

    @staticmethod
    async def _log_lead_capture(
        session: AsyncSession,
        *,
        submission_id: uuid.UUID,
        vendor_name: str,
        email: str,
        name: str | None,
    ) -> None:
        """Insert a lead-capture event directly via raw SQL.

        This is a lightweight audit record; we intentionally avoid creating
        a full ORM model for it to keep the schema migration footprint small.
        """
        now = datetime.now(timezone.utc)
        await session.execute(
            text(
                """
                INSERT INTO lead_captures (id, vendor_name, email, name, captured_at)
                VALUES (:id, :vendor_name, :email, :name, :captured_at)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": uuid.uuid4(),
                "vendor_name": vendor_name,
                "email": email,
                "name": name,
                "captured_at": now,
            },
        )

    @staticmethod
    async def _send_confirmation_email(
        *,
        to_email: str,
        vendor_name: str,
        display_name: str,
    ) -> None:
        """Send a submission confirmation email to the submitter."""
        try:
            from app.infrastructure.email import email_client

            subject = f"Reliastra — Vendor Submission Received: {display_name}"
            body = (
                f"Hi there,\n\n"
                f"Thank you for submitting '{display_name}' ({vendor_name}) to Reliastra.\n\n"
                f"Your submission is currently pending review. Our team typically reviews "
                f"new vendor submissions within 3 business days. You will receive another "
                f"email once a decision has been made.\n\n"
                f"If you have any questions, reply to this email.\n\n"
                f"Best regards,\n"
                f"The Reliastra Team"
            )
            email_client.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            logger.warning("Failed to send confirmation email to %s: %s", to_email, exc)

    @staticmethod
    async def _send_review_email(
        *,
        to_email: str,
        vendor_name: str,
        display_name: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        """Send an approval / rejection notification email to the submitter."""
        try:
            from app.infrastructure.email import email_client

            if status == "approved":
                subject = f"Reliastra — Vendor Approved: {display_name}"
                body = (
                    f"Hi there,\n\n"
                    f"Great news! Your vendor submission '{display_name}' ({vendor_name}) "
                    f"has been approved and added to Reliastra.\n\n"
                    f"You can now view its status page and monitoring data.\n\n"
                    f"Thank you for contributing to better infrastructure visibility.\n\n"
                    f"Best regards,\n"
                    f"The Reliastra Team"
                )
            else:
                subject = f"Reliastra — Vendor Submission Update: {display_name}"
                body = (
                    f"Hi there,\n\n"
                    f"Your vendor submission '{display_name}' ({vendor_name}) "
                    f"has been reviewed but was not approved at this time.\n\n"
                    f"Reason: {reason or 'No additional details provided.'}\n\n"
                    f"You are welcome to resubmit with additional information if you believe "
                    f"this decision should be reconsidered.\n\n"
                    f"Best regards,\n"
                    f"The Reliastra Team"
                )
            email_client.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            logger.warning("Failed to send review email to %s: %s", to_email, exc)


# Singleton instance
vendor_submission_service = VendorSubmissionService()
