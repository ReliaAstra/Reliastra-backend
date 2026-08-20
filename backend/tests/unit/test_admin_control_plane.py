"""Unit tests for the admin control-plane surface.

These tests validate route registration and schema shape without a live DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.main import app
from app.modules.admin.control_plane_schemas import (
    AdminOverviewResponse,
    AttentionItem,
    AttentionResponse,
    CustomerDetailResponse,
    CustomerListItem,
    GrowthFunnelResponse,
    GrowthFunnelStage,
    OverviewBusinessSection,
    ProductFeatureItem,
    RevenueSummaryResponse,
)


def _admin_paths() -> dict[str, set[str]]:
    schema = app.openapi()
    result: dict[str, set[str]] = {}
    for path, methods in schema.get("paths", {}).items():
        if "/admin" not in path:
            continue
        result[path] = {m.upper() for m in methods.keys() if m.upper() != "HEAD"}
    return result


def test_canonical_overview_and_attention_registered():
    paths = _admin_paths()
    assert "GET" in paths.get("/v1/admin/overview", set())
    assert "GET" in paths.get("/v1/admin/attention", set())
    assert "GET" in paths.get("/v1/admin/search", set())


def test_customers_control_plane_registered():
    paths = _admin_paths()
    assert "GET" in paths["/v1/admin/customers"]
    assert "GET" in paths["/v1/admin/customers/recent"]
    assert "GET" in paths["/v1/admin/customers/churn-risk"]
    assert "GET" in paths["/v1/admin/customers/{customer_id}"]
    assert "PATCH" in paths["/v1/admin/customers/{customer_id}"]
    assert "POST" in paths["/v1/admin/customers/{customer_id}/impersonate"]
    assert "POST" in paths["/v1/admin/customers/{customer_id}/plan"]
    assert "POST" in paths["/v1/admin/customers/{customer_id}/email"]
    assert "POST" in paths["/v1/admin/customers/{customer_id}/deactivate"]
    assert "GET" in paths["/v1/admin/customers/{customer_id}/activity"]


def test_revenue_growth_product_registered():
    paths = _admin_paths()
    for p in (
        "/v1/admin/revenue/summary",
        "/v1/admin/revenue/timeseries",
        "/v1/admin/revenue/attention",
        "/v1/admin/growth/overview",
        "/v1/admin/growth/funnel",
        "/v1/admin/growth/retention",
        "/v1/admin/growth/referrals",
        "/v1/admin/product/overview",
        "/v1/admin/product/features",
        "/v1/admin/product/vendors",
        "/v1/admin/product/engagement",
        "/v1/admin/product/activation",
    ):
        assert "GET" in paths.get(p, set()), f"missing {p}"


def test_support_communications_operations_registered():
    paths = _admin_paths()
    assert "GET" in paths["/v1/admin/support/overview"]
    assert "GET" in paths["/v1/admin/support/tickets"]
    assert "GET" in paths["/v1/admin/communications/overview"]
    assert "GET" in paths["/v1/admin/operations/overview"]
    assert "GET" in paths["/v1/admin/operations/errors"]
    assert "GET" in paths["/v1/admin/operations/metrics"]
    assert "GET" in paths["/v1/admin/audit-log"]


def test_partners_surface_unchanged():
    paths = _admin_paths()
    assert "GET" in paths["/v1/admin/partners"]
    assert "GET" in paths["/v1/admin/partners/stats"]
    assert "GET" in paths["/v1/admin/partners/commissions"]
    assert "POST" in paths["/v1/admin/partners/payouts"]
    assert "POST" in paths["/v1/admin/partners/commissions/{commission_id}/reverse"]
    assert "POST" in paths["/v1/admin/partners/payouts/{payout_id}/process"]


def test_legacy_endpoints_marked_deprecated():
    schema = app.openapi()
    deprecated_paths = [
        "/v1/admin/business/summary",
        "/v1/admin/business/mrr-timeseries",
        "/v1/admin/business/recent-signups",
        "/v1/admin/business/churn-signals",
        "/v1/admin/analytics/growth-funnel",
        "/v1/admin/analytics/feature-adoption",
        "/v1/admin/analytics/vendor-coverage",
        "/v1/admin/analytics/time-to-value",
        "/v1/admin/analytics/engagement",
        "/v1/admin/analytics/retention",
        "/v1/admin/users",
        "/v1/admin/users/override-plan",
        "/v1/admin/operations/health",
        "/v1/admin/operations/error-logs",
        "/v1/admin/growth/top-vendors",
        "/v1/admin/growth/referral-stats",
    ]
    for path in deprecated_paths:
        methods = schema["paths"][path]
        # at least one method must be deprecated
        assert any(
            methods[m].get("deprecated") for m in methods if m != "parameters"
        ), f"{path} should be deprecated"


def test_overview_schema_sections():
    now = datetime.now(timezone.utc)
    payload = AdminOverviewResponse(
        business=OverviewBusinessSection(users=10, mrr=99.0, arr_estimate=1188.0),
        actions_required=[
            AttentionItem(
                type="urgent_support",
                priority="critical",
                count=2,
                title="2 urgent support ticket(s)",
            )
        ],
        generated_at=now,
    )
    data = payload.model_dump()
    assert "business" in data
    assert "growth" in data
    assert "product" in data
    assert "support" in data
    assert "communications" in data
    assert "system" in data
    assert "actions_required" in data
    assert data["business"]["arr_estimate"] == 1188.0
    assert data["actions_required"][0]["priority"] == "critical"


def test_attention_response_counts():
    now = datetime.now(timezone.utc)
    resp = AttentionResponse(
        items=[
            AttentionItem(type="a", priority="critical", count=1, title="c"),
            AttentionItem(type="b", priority="high", count=3, title="h"),
            AttentionItem(type="c", priority="normal", count=5, title="n"),
        ],
        critical_count=1,
        high_count=1,
        normal_count=1,
        generated_at=now,
    )
    assert resp.critical_count == 1
    assert len(resp.items) == 3


def test_customer_list_item_health_values():
    item = CustomerListItem(
        customer_id="00000000-0000-0000-0000-000000000001",
        email="a@b.com",
        full_name="Ada",
        is_active=True,
        health="at_risk",
        created_at=datetime.now(timezone.utc),
    )
    assert item.health == "at_risk"


def test_revenue_summary_defaults():
    s = RevenueSummaryResponse(mrr=100.0, arr_estimate=1200.0, paying_customers=5, arpu=20.0)
    assert s.currency == "USD"
    assert s.net_new_mrr == 0.0


def test_growth_funnel_stages():
    funnel = GrowthFunnelResponse(
        period="30d",
        stages=[
            GrowthFunnelStage(stage="signup", count=100),
            GrowthFunnelStage(stage="paid", count=10, conversion_from_previous=0.1),
        ],
    )
    assert funnel.stages[0].stage == "signup"
    assert funnel.stages[1].conversion_from_previous == 0.1


def test_product_feature_adoption_rate():
    f = ProductFeatureItem(feature="monitoring", eligible=100, adopted=42, adoption_rate=0.42)
    assert f.adoption_rate == 0.42


def test_customer_detail_requires_core_fields():
    detail = CustomerDetailResponse(
        customer_id="00000000-0000-0000-0000-000000000002",
        email="c@d.com",
        full_name="Grace",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    assert detail.organizations == []
    assert detail.mrr == 0.0


def test_home_bootstrap_request_count_target():
    """Admin home should be coverable by a small set of endpoints."""
    home_endpoints = {
        "/v1/admin/overview",
        "/v1/admin/attention",
        "/v1/admin/revenue/timeseries",
        "/v1/admin/customers/recent",
    }
    paths = _admin_paths()
    for ep in home_endpoints:
        assert ep in paths
