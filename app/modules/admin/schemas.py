from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Shared / Generic
# =============================================================================

class PaginatedResponse(BaseModel):
    """Standard paginated list response."""
    items: list[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class MessageResponse(BaseModel):
    message: str


class BulkActionResponse(BaseModel):
    updated_count: int
    message: str


# =============================================================================
# Business Dashboard Schemas
# =============================================================================

class BusinessSummaryResponse(BaseModel):
    total_users: int = 0
    total_organizations: int = 0
    mrr: float = 0.0
    active_subscriptions: int = 0
    new_signups_7d: int = 0
    churned_7d: int = 0


class MRRDataPoint(BaseModel):
    date: str
    mrr: float


class MRRTimeSeriesResponse(BaseModel):
    data_points: list[MRRDataPoint] = []


class RecentSignup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    org_name: str | None = None
    plan: str | None = None
    source: str | None = None
    created_at: datetime


class RecentSignupsResponse(BaseModel):
    items: list[RecentSignup] = []


class ChurnSignal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: uuid.UUID
    org_name: str
    plan: str
    last_activity_at: datetime | None = None
    subscription_status: str | None = None
    risk_level: str = "low"


class ChurnSignalsResponse(BaseModel):
    items: list[ChurnSignal] = []


class FoundingCustomer(BaseModel):
    org_id: uuid.UUID
    org_name: str
    plan: str
    founding_discount_pct: int
    member_count: int
    created_at: datetime


class FoundingCustomersResponse(BaseModel):
    items: list[FoundingCustomer] = []


# =============================================================================
# Analytics Dashboard Schemas
# =============================================================================

class GrowthFunnelResponse(BaseModel):
    stage: str
    count: int


class GrowthFunnelData(BaseModel):
    stages: list[GrowthFunnelResponse] = []


class RetentionCohort(BaseModel):
    cohort: str
    cohort_size: int
    week_1: float = 0.0
    week_2: float = 0.0
    week_4: float = 0.0
    week_8: float = 0.0


class RetentionData(BaseModel):
    cohorts: list[RetentionCohort] = []


class FeatureAdoptionItem(BaseModel):
    feature: str
    total_users: int = 0
    active_users: int = 0
    adoption_pct: float = 0.0


class FeatureAdoptionResponse(BaseModel):
    features: list[FeatureAdoptionItem] = []


class VendorCoverageItem(BaseModel):
    vendor_name: str
    total_orgs: int = 0
    monitoring_orgs: int = 0
    coverage_pct: float = 0.0


class VendorCoverageResponse(BaseModel):
    vendors: list[VendorCoverageItem] = []


class TimeToValueBucket(BaseModel):
    bucket: str
    count: int = 0


class TimeToValueResponse(BaseModel):
    buckets: list[TimeToValueBucket] = []


class EngagementMetric(BaseModel):
    dau: int = 0
    wau: int = 0
    mau: int = 0
    dau_mau_ratio: float = 0.0


class EngagementResponse(BaseModel):
    metrics: EngagementMetric


# =============================================================================
# Users Dashboard Schemas
# =============================================================================

class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_system_admin: bool
    source: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class AdminUserOrgInfo(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str
    plan: str


class AdminUserDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_email_verified: bool
    is_system_admin: bool
    is_superuser: bool
    avatar_url: str | None = None
    auth_provider: str | None = None
    source: str | None = None
    admin_note: str | None = None
    last_login_at: datetime | None = None
    last_activity_at: datetime | None = None
    login_count: int = 0
    created_at: datetime
    updated_at: datetime
    organizations: list[AdminUserOrgInfo] = []


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    is_system_admin: bool | None = None
    admin_note: str | None = None
    source: str | None = None


class ImpersonationTokenResponse(BaseModel):
    token: str
    impersonated_user_id: uuid.UUID
    impersonated_email: str
    expires_in_seconds: int


class OverridePlanRequest(BaseModel):
    org_id: uuid.UUID
    new_plan: str
    reason: str | None = None


class AdminSendEmailRequest(BaseModel):
    user_id: uuid.UUID
    subject: str
    body: str
    html_body: str | None = None


class UserActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class UserActivityResponse(BaseModel):
    items: list[UserActivityItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


# =============================================================================
# Communications Dashboard Schemas
# =============================================================================

# -- Email Campaigns --

class EmailCampaignCreateRequest(BaseModel):
    campaign_name: str
    subject: str
    body_html: str
    body_text: str | None = None
    segment: str | None = None
    utm_campaign: str | None = None
    scheduled_at: datetime | None = None


class EmailCampaignUpdateRequest(BaseModel):
    campaign_name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    segment: str | None = None


class EmailCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_name: str
    subject: str
    body_html: str
    body_text: str | None = None
    segment: str | None = None
    recipient_count: int = 0
    sent_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    bounced_count: int = 0
    failed_count: int = 0
    status: str = "draft"
    utm_campaign: str | None = None
    created_by: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EmailCampaignListResponse(BaseModel):
    items: list[EmailCampaignResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class EmailCampaignSendResponse(BaseModel):
    message: str
    campaign_id: uuid.UUID
    recipient_count: int


# -- In-App Notifications --

class InAppNotificationCreateRequest(BaseModel):
    title: str
    body: str
    notification_type: str = "info"
    action_url: str | None = None
    action_label: str | None = None
    priority: str = "normal"
    expires_at: datetime | None = None
    is_dismissible: bool = True
    target_segment: str | None = None
    target_plan: str | None = None


class InAppNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    notification_type: str = "info"
    action_url: str | None = None
    action_label: str | None = None
    priority: str = "normal"
    expires_at: datetime | None = None
    is_dismissible: bool = True
    created_by: uuid.UUID | None = None
    created_at: datetime


class InAppNotificationListResponse(BaseModel):
    items: list[InAppNotificationResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class InAppNotificationPublishResponse(BaseModel):
    message: str
    notification_id: uuid.UUID
    delivery_count: int


# -- Announcements --

class AnnouncementCreateRequest(BaseModel):
    title: str
    body_html: str
    placement: str = "top_banner"
    target_plans: list[str] | None = None
    target_segment: str | None = None
    action_url: str | None = None
    action_label: str | None = None
    is_dismissible: bool = True
    bg_color: str | None = None
    text_color: str | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = None
    body_html: str | None = None
    placement: str | None = None
    target_plans: list[str] | None = None
    target_segment: str | None = None
    action_url: str | None = None
    action_label: str | None = None
    is_dismissible: bool | None = None
    bg_color: str | None = None
    text_color: str | None = None
    is_active: bool | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body_html: str
    placement: str = "top_banner"
    target_plans: list[str] | None = None
    target_segment: str | None = None
    action_url: str | None = None
    action_label: str | None = None
    is_dismissible: bool = True
    bg_color: str | None = None
    text_color: str | None = None
    impression_count: int = 0
    dismissal_count: int = 0
    click_count: int = 0
    is_active: bool = False
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


# Public-facing announcement (for /v1/announcements)
class PublicAnnouncement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body_html: str
    placement: str = "top_banner"
    action_url: str | None = None
    action_label: str | None = None
    is_dismissible: bool = True
    bg_color: str | None = None
    text_color: str | None = None


class PublicAnnouncementsResponse(BaseModel):
    announcements: list[PublicAnnouncement] = []


# =============================================================================
# Operations Dashboard Schemas
# =============================================================================

class HealthCheckItem(BaseModel):
    component: str
    status: str
    latency_ms: float | None = None
    message: str | None = None


class HealthCheckResponse(BaseModel):
    overall: str = "ok"
    checks: list[HealthCheckItem] = []


class CheckEngineItem(BaseModel):
    name: str
    status: str
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_error: str | None = None


class CheckEnginesResponse(BaseModel):
    engines: list[CheckEngineItem] = []


class ErrorLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: str
    component: str | None = None
    message: str
    stack_trace: str | None = None
    request_id: str | None = None
    user_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    ip_address: str | None = None
    is_resolved: bool = False
    created_at: datetime


class ErrorLogListResponse(BaseModel):
    items: list[ErrorLogItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class SystemMetrics(BaseModel):
    total_users: int = 0
    total_orgs: int = 0
    total_dependencies: int = 0
    total_incidents_open: int = 0
    total_tickets_open: int = 0
    db_pool_size: int = 0
    db_pool_checked_out: int = 0
    db_pool_overflow: int = 0


# =============================================================================
# Support / Feedback Schemas
# =============================================================================

class FeedbackTicketCreateRequest(BaseModel):
    email: str
    full_name: str | None = None
    category: str = "general"
    subject: str
    body: str
    priority: str = "normal"
    source: str | None = None


class FeedbackTicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None
    resolution: str | None = None


class FeedbackMessageCreateRequest(BaseModel):
    body: str
    is_internal_note: bool = False


class FeedbackTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_number: str
    user_id: uuid.UUID | None = None
    email: str
    full_name: str | None = None
    category: str
    subject: str
    body: str
    priority: str
    status: str
    source: str | None = None
    assigned_to: uuid.UUID | None = None
    resolution: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class FeedbackMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_type: str
    sender_id: uuid.UUID
    sender_name: str
    body: str
    is_internal_note: bool
    created_at: datetime


class FeedbackTicketDetailResponse(BaseModel):
    ticket: FeedbackTicketResponse
    messages: list[FeedbackMessageResponse] = []


class FeedbackTicketListResponse(BaseModel):
    items: list[FeedbackTicketResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class FeedbackBulkUpdateRequest(BaseModel):
    ticket_ids: list[uuid.UUID]
    status: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None


class FeedbackStatsResponse(BaseModel):
    total_tickets: int = 0
    open_tickets: int = 0
    resolved_tickets: int = 0
    avg_resolution_hours: float = 0.0
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}


# =============================================================================
# Audit Log Schemas
# =============================================================================

class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_user_id: uuid.UUID | None = None
    admin_email: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
