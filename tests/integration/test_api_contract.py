from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import settings_factory

REQUIRED_ROUTES = {
    ("POST", "/v1/auth/register"),
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/logout"),
    ("GET", "/v1/users/me"),
    ("PATCH", "/v1/users/me"),
    ("GET", "/v1/orgs/"),
    ("POST", "/v1/orgs/"),
    ("GET", "/v1/orgs/{org_id}"),
    ("PATCH", "/v1/orgs/{org_id}"),
    ("GET", "/v1/orgs/{org_id}/members"),
    ("POST", "/v1/orgs/{org_id}/members"),
    ("PATCH", "/v1/orgs/{org_id}/members/{member_id}"),
    ("DELETE", "/v1/orgs/{org_id}/members/{member_id}"),
    ("GET", "/v1/orgs/{org_id}/dependencies/"),
    ("POST", "/v1/orgs/{org_id}/dependencies/"),
    ("GET", "/v1/orgs/{org_id}/dependencies/{dep_id}"),
    ("PATCH", "/v1/orgs/{org_id}/dependencies/{dep_id}"),
    ("DELETE", "/v1/orgs/{org_id}/dependencies/{dep_id}"),
    ("GET", "/v1/orgs/{org_id}/dependencies/{dep_id}/results"),
    ("GET", "/v1/orgs/{org_id}/dependencies/{dep_id}/history"),
    ("GET", "/v1/orgs/{org_id}/incidents/"),
    ("GET", "/v1/orgs/{org_id}/incidents/{inc_id}"),
    ("PATCH", "/v1/orgs/{org_id}/incidents/{inc_id}"),
    ("POST", "/v1/orgs/{org_id}/incidents/{inc_id}/correlate"),
    ("GET", "/v1/orgs/{org_id}/incidents/{inc_id}/evidence"),
    ("GET", "/v1/orgs/{org_id}/evidence/"),
    ("GET", "/v1/orgs/{org_id}/evidence/{report_id}"),
    ("POST", "/v1/orgs/{org_id}/evidence/{report_id}/regenerate"),
    ("GET", "/v1/public/vendors/"),
    ("GET", "/v1/public/vendors/{vendor_name}"),
    ("GET", "/v1/public/vendors/{vendor_name}/history"),
    ("GET", "/v1/orgs/{org_id}/dashboard/summary"),
    ("GET", "/v1/orgs/{org_id}/dashboard/dependency-health"),
    ("GET", "/v1/orgs/{org_id}/dashboard/incident-timeline"),
    ("GET", "/v1/orgs/{org_id}/dashboard/vendor-status"),
    ("GET", "/v1/orgs/{org_id}/notifications/configs"),
    ("POST", "/v1/orgs/{org_id}/notifications/configs"),
    ("GET", "/v1/orgs/{org_id}/notifications/configs/{config_id}"),
    ("PATCH", "/v1/orgs/{org_id}/notifications/configs/{config_id}"),
    ("DELETE", "/v1/orgs/{org_id}/notifications/configs/{config_id}"),
    ("POST", "/v1/orgs/{org_id}/notifications/test"),
    ("GET", "/v1/orgs/{org_id}/api-keys/"),
    ("POST", "/v1/orgs/{org_id}/api-keys/"),
    ("DELETE", "/v1/orgs/{org_id}/api-keys/{key_id}"),
}


def test_openapi_contains_every_mvp_endpoint() -> None:
    schema = create_app(settings_factory()).openapi()
    actual = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method != "parameters"
    }
    assert REQUIRED_ROUTES <= actual


def test_health_endpoint() -> None:
    app = create_app(settings_factory())
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_error_envelopes_cover_validation_and_unknown_routes() -> None:
    app = create_app(settings_factory())
    with TestClient(app) as client:
        invalid = client.post("/v1/auth/register", json={"email": "not-an-email"})
        missing = client.get("/does-not-exist")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
