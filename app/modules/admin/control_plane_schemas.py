"""Control-plane response/request schemas for the admin operating console.

These schemas power the consolidated admin API surface:

    overview → customers → revenue → growth → product
    → support → communications → operations → audit → attention
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Shared building blocks
# =============================================================================

class ComponentHealth(BaseModel):
    status: str = "unknown"  # healthy | degraded | error | unknown
    latency_ms: float | None = None
    last_checked: datetime | None = None
    error: str | None = None
    message: str | None = None


class AttentionItem(BaseModel):
    type: str
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    count: int = 0
    title: str
    description: str | None = None
    target_resource: str | None = None
    target_id: str | None = None
    href: str | None = None


class SearchHit(BaseModel):
    resource_type: str
    id: str
    title: str
    subtitle: str | None = None
    href: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Overview
# =============================================================================

class OverviewBusinessSection(BaseModel):
    users: int = 0
    organizations: int = 0
    active_users: int = 0
    active_organizations: int = 0
    paying_organizations: int = 0
    mrr: float = 0.0
    arr_estimate: float = 0.0
    new_signups: int = 0
    new_paying_customers: int = 0
    churn_count: int = 0
    churn_rate: float = 0.0


class OverviewGrowthSection(BaseModel):
    signup_growth: float = 0.0
    customer_growth: float = 0.0
    mrr_growth: float = 0.0
    conversion_rate: float = 0.0


class OverviewProductSection(BaseModel):
    monitors: int = 0
    active_monitors: int = 0
    dependencies: int = 0
    checks_today: int = 0
    incidents: int = 0
    open_incidents: int = 0


class OverviewSupportSection(BaseModel):
    open_tickets: int = 0
    urgent_tickets: int = 0
    unassigned_tickets: int = 0
    average_response_time_hours: float = 0.0


class OverviewCommunicationsSection(BaseModel):
    active_campaigns: int = 0
    scheduled_campaigns: int = 0
    draft_campaigns: int = 0
    recent_announcements: int = 0


class OverviewSystemSection(BaseModel):
    api_health: ComponentHealth = Field(default_factory=ComponentHealth)
    database_health: ComponentHealth = Field(default_factory=ComponentHealth)
    redis_health: ComponentHealth = Field(default_factory=ComponentHealth)
    worker_health: ComponentHealth = Field(default_factory=ComponentHealth)
    scheduler_health: ComponentHealth = Field(default_factory=ComponentHealth)


class AdminOverviewResponse(BaseModel):
    """Primary admin bootstrap payload — one request for the home screen."""

    business: OverviewBusinessSection = Field(default_factory=OverviewBusinessSection)
    growth: OverviewGrowthSection = Field(default_factory=OverviewGrowthSection)
    product: OverviewProductSection = Field(default_factory=OverviewProductSection)
    support: OverviewSupportSection = Field(default_factory=OverviewSupportSection)
    communications: OverviewCommunicationsSection = Field(
        default_factory=OverviewCommunicationsSection
    )
    system: OverviewSystemSection = Field(default_factory=OverviewSystemSection)
    actions_required: list[AttentionItem] = Field(default_factory=list)
    generated_at: datetime


class AttentionResponse(BaseModel):
    items: list[AttentionItem] = Field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    normal_count: int = 0
    generated_at: datetime


class AdminSearchResponse(BaseModel):
    query: str
    customers: list[SearchHit] = Field(default_factory=list)
    organizations: list[SearchHit] = Field(default_factory=list)
    tickets: list[SearchHit] = Field(default_factory=list)
    partners: list[SearchHit] = Field(default_factory=list)
    campaigns: list[SearchHit] = Field(default_factory=list)
    total: int = 0


# =============================================================================
# Customers
# =============================================================================

class CustomerListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    source: str | None = None
    plan: str | None = None
    org_id: uuid.UUID | None = None
    org_name: str | None = None
    health: str = "unknown"  # healthy | at_risk | churning | inactive
    mrr: float = 0.0
    last_activity_at: datetime | None = None
    created_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class CustomerOrgSnapshot(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str
    plan: str
    mrr: float = 0.0
    billing_status: str | None = None
    member_count: int = 0
    dependency_count: int = 0
    open_incidents: int = 0
    open_tickets: int = 0


class CustomerDetailResponse(BaseModel):
    """Consolidated customer workspace snapshot."""

    customer_id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_email_verified: bool = False
    is_system_admin: bool = False
    avatar_url: str | None = None
    auth_provider: str | None = None
    source: str | None = None
    admin_note: str | None = None
    health: str = "unknown"
    last_login_at: datetime | None = None
    last_activity_at: datetime | None = None
    login_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    organizations: list[CustomerOrgSnapshot] = Field(default_factory=list)
    primary_org: CustomerOrgSnapshot | None = None
    plan: str | None = None
    mrr: float = 0.0
    billing_status: str | None = None
    subscription: dict[str, Any] | None = None

    dependencies: int = 0
    monitors: int = 0
    incidents: int = 0
    open_incidents: int = 0
    support_tickets: int = 0
    open_support_tickets: int = 0

    recent_activity: list[dict[str, Any]] = Field(default_factory=list)
    recent_tickets: list[dict[str, Any]] = Field(default_factory=list)


class CustomerUpdateRequest(BaseModel):
    """Safe profile-state updates only — no high-impact side effects."""

    full_name: str | None = None
    admin_note: str | None = None
    source: str | None = None


class CustomerPlanRequest(BaseModel):
    plan: str
    reason: str | None = None
    org_id: uuid.UUID | None = None  # defaults to primary org


class CustomerEmailRequest(BaseModel):
    subject: str
    body: str
    html_body: str | None = None


class CustomerImpersonateRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class CustomerImpersonateResponse(BaseModel):
    token: str
    impersonated_user_id: uuid.UUID
    impersonated_email: str
    expires_in_seconds: int
    impersonator_id: uuid.UUID
    reason: str
    no_refresh_token: bool = True


class CustomerDeactivateRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


# =============================================================================
# Revenue
# =============================================================================

class RevenueSummaryResponse(BaseModel):
    mrr: float = 0.0
    mrr_growth: float = 0.0
    arr_estimate: float = 0.0
    new_mrr: float = 0.0
    expansion_mrr: float = 0.0
    contraction_mrr: float = 0.0
    churned_mrr: float = 0.0
    net_new_mrr: float = 0.0
    paying_customers: int = 0
    arpu: float = 0.0
    currency: str = "USD"


class RevenueDataPoint(BaseModel):
    date: str
    mrr: float = 0.0
    paying_customers: int | None = None


class RevenueTimeseriesResponse(BaseModel):
    period: str
    granularity: str
    data_points: list[RevenueDataPoint] = Field(default_factory=list)


class RevenueAttentionResponse(BaseModel):
    failed_payments: list[AttentionItem] = Field(default_factory=list)
    revenue_drop_alerts: list[AttentionItem] = Field(default_factory=list)
    unusual_mrr_changes: list[AttentionItem] = Field(default_factory=list)
    high_value_churn: list[AttentionItem] = Field(default_factory=list)
    items: list[AttentionItem] = Field(default_factory=list)


# =============================================================================
# Growth
# =============================================================================

class GrowthOverviewResponse(BaseModel):
    signups: int = 0
    activated_users: int = 0
    activated_organizations: int = 0
    paying_customers: int = 0
    conversion_rate: float = 0.0
    mrr_growth: float = 0.0
    retention_summary: dict[str, Any] = Field(default_factory=dict)
    engagement: dict[str, Any] = Field(default_factory=dict)
    period: str = "30d"


class GrowthFunnelStage(BaseModel):
    stage: str
    count: int = 0
    conversion_from_previous: float | None = None


class GrowthFunnelResponse(BaseModel):
    period: str = "all"
    stages: list[GrowthFunnelStage] = Field(default_factory=list)
    # Optional PLG funnel metrics when available
    plg: dict[str, Any] | None = None


class GrowthReferralsResponse(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    top_referrers: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Product
# =============================================================================

class ProductOverviewResponse(BaseModel):
    active_users: int = 0
    active_organizations: int = 0
    active_monitors: int = 0
    checks: int = 0
    checks_today: int = 0
    incidents: int = 0
    open_incidents: int = 0
    dependencies: int = 0
    vendor_coverage_top: list[dict[str, Any]] = Field(default_factory=list)
    feature_adoption: list[dict[str, Any]] = Field(default_factory=list)
    time_to_value: dict[str, Any] = Field(default_factory=dict)
    engagement: dict[str, Any] = Field(default_factory=dict)


class ProductFeatureItem(BaseModel):
    feature: str
    eligible: int = 0
    adopted: int = 0
    adoption_rate: float = 0.0


class ProductFeaturesResponse(BaseModel):
    features: list[ProductFeatureItem] = Field(default_factory=list)


class ProductVendorItem(BaseModel):
    vendor: str
    organizations_using: int = 0
    coverage_percentage: float = 0.0
    incidents: int = 0
    monitoring_volume: int = 0
    views: int | None = None
    badge_embeds: int | None = None
    submissions: int | None = None
    evidence_downloads: int | None = None


class ProductVendorsResponse(BaseModel):
    vendors: list[ProductVendorItem] = Field(default_factory=list)


class ProductEngagementResponse(BaseModel):
    dau: int = 0
    wau: int = 0
    mau: int = 0
    stickiness: float = 0.0  # dau/mau


class ProductActivationResponse(BaseModel):
    median_time_to_first_check_hours: float | None = None
    p25_hours: float | None = None
    p50_hours: float | None = None
    p75_hours: float | None = None
    activation_rate: float = 0.0
    buckets: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Support overview
# =============================================================================

class SupportOverviewResponse(BaseModel):
    open: int = 0
    urgent: int = 0
    unassigned: int = 0
    waiting_on_customer: int = 0
    waiting_on_agent: int = 0
    resolved_today: int = 0
    average_first_response_hours: float = 0.0
    average_resolution_hours: float = 0.0
    sla_breaches: int = 0
    queue: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)


class SupportTicketWorkspaceResponse(BaseModel):
    """Complete support workspace — ticket + customer context."""

    ticket: dict[str, Any]
    messages: list[dict[str, Any]] = Field(default_factory=list)
    customer: dict[str, Any] | None = None
    organization: dict[str, Any] | None = None
    subscription: dict[str, Any] | None = None
    recent_customer_activity: list[dict[str, Any]] = Field(default_factory=list)
    related_incidents: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Communications overview
# =============================================================================

class CommunicationsOverviewResponse(BaseModel):
    campaigns_total: int = 0
    drafts: int = 0
    scheduled: int = 0
    sent_today: int = 0
    notifications: int = 0
    announcements_active: int = 0
    announcements_total: int = 0
    recent_delivery_stats: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Operations overview
# =============================================================================

class OperationsOverviewResponse(BaseModel):
    api: ComponentHealth = Field(default_factory=ComponentHealth)
    database: ComponentHealth = Field(default_factory=ComponentHealth)
    redis: ComponentHealth = Field(default_factory=ComponentHealth)
    workers: ComponentHealth = Field(default_factory=ComponentHealth)
    scheduler: ComponentHealth = Field(default_factory=ComponentHealth)
    check_engine: ComponentHealth = Field(default_factory=ComponentHealth)
    billing: ComponentHealth = Field(default_factory=ComponentHealth)
    email: ComponentHealth = Field(default_factory=ComponentHealth)
    storage: ComponentHealth = Field(default_factory=ComponentHealth)
    overall: str = "unknown"
    engines: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime
