#!/usr/bin/env python3
"""Reliastra deep functional test suite — exercises the FULL public API surface.

Runs against a live stack (uvicorn + celery worker + celery beat + PG + Redis).
Emits a pass/fail table to stdout and a JSON artifact to audit/results/.

Endpoint substitutions (httpbin.org is unreachable from the CI sandbox):
  dep1 healthy   -> https://api.github.com/zen                  (200)
  dep2 "500"     -> https://api.github.com/repos/<nope>         (404 -> unhealthy, same semantics as 500)
  dep3 slow      -> https://files.pythonhosted.org/.../torch*.whl (760MB -> timeout with timeout_seconds=3)
  dep4 redirect  -> http://api.github.com/zen                   (301 -> tests redirect handling)
  dep5 refused   -> http://localhost:9999/nonexistent           (SSRF-blocked -> is_up=false)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

BASE = os.environ.get("RELI ASTRA_BASE", "http://localhost:8000").replace(" ", "")
BASE = os.environ.get("RELI_ASTRA_BASE", "http://localhost:8000")
RESULTS: list[dict] = []
client = httpx.Client(timeout=30.0, follow_redirects=True)


def check(name: str, passed: bool, detail: str = "", severity: str = "info", group: str = "") -> bool:
    RESULTS.append({
        "group": group, "name": name, "pass": bool(passed),
        "detail": str(detail)[:500], "severity": severity,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name} :: {detail}")
    return passed


def req(method: str, path: str, **kw) -> httpx.Response:
    r = client.request(method, f"{BASE}{path}", **kw)
    return r


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def main() -> None:
    email = f"owner-{uuid.uuid4().hex[:8]}@test.reliastra.dev"
    pw = "Str0ng-Passw0rd!"
    viewer_email = f"viewer-{uuid.uuid4().hex[:8]}@test.reliastra.dev"
    member_email = f"member-{uuid.uuid4().hex[:8]}@test.reliastra.dev"

    # ─────────────────────────── AUTH ───────────────────────────
    g = "Auth"
    r = req("POST", "/v1/auth/register", json={
        "email": email, "password": pw, "full_name": "Owner One", "org_name": "Acme Corp"})
    tok_ok = r.status_code == 201 and all(k in r.json() for k in ("access_token", "refresh_token", "token_type", "expires_in"))
    check("POST /v1/auth/register -> 201 TokenResponse", tok_ok, f"status={r.status_code} body={r.text[:200]}", group=g)
    if not tok_ok:
        print("ABORT: cannot register primary user"); sys.exit(1)
    owner_tok, refresh_tok = r.json()["access_token"], r.json()["refresh_token"]

    r = req("POST", "/v1/auth/login", json={"email": email, "password": pw})
    check("POST /v1/auth/login -> new tokens", r.status_code == 200 and r.json().get("access_token"), f"status={r.status_code}", group=g)
    owner_tok2 = r.json().get("access_token", "")

    r = req("POST", "/v1/auth/refresh", json={"refresh_token": refresh_tok})
    ref_ok = r.status_code == 200 and r.json().get("access_token") and r.json().get("refresh_token")
    check("POST /v1/auth/refresh -> rotated tokens", ref_ok, f"status={r.status_code}", group=g)
    refresh_tok2 = r.json().get("refresh_token", refresh_tok)

    r = req("POST", "/v1/auth/logout", json={"refresh_token": refresh_tok2})
    check("POST /v1/auth/logout -> 204 + revocation", r.status_code == 204, f"status={r.status_code}", group=g)
    r = req("POST", "/v1/auth/refresh", json={"refresh_token": refresh_tok2})
    check("Refreshing a revoked token is rejected", r.status_code in (401, 403), f"status={r.status_code}", group=g)

    # Register viewer + member
    r = req("POST", "/v1/auth/register", json={"email": viewer_email, "password": pw, "full_name": "Viewer One"})
    viewer_tok = r.json().get("access_token", "")
    check("Register viewer user", r.status_code == 201 and bool(viewer_tok), f"status={r.status_code}", group=g)
    r = req("POST", "/v1/auth/register", json={"email": member_email, "password": pw, "full_name": "Member One"})
    member_tok = r.json().get("access_token", "")
    check("Register member user", r.status_code == 201 and bool(member_tok), f"status={r.status_code}", group=g)

    # ─────────────────────────── ORGS & RBAC ───────────────────────────
    g = "Orgs & RBAC"
    r = req("POST", "/v1/orgs", json={"name": "Acme Corp", "slug": f"acme-{uuid.uuid4().hex[:6]}"}, headers=bearer(owner_tok))
    org_ok = r.status_code == 201 and "id" in r.json()
    check("POST /v1/orgs -> create org", org_ok, f"status={r.status_code}", group=g)
    org_id = r.json().get("id", "")

    r = req("GET", "/v1/orgs", headers=bearer(owner_tok))
    check("GET /v1/orgs -> list w/ role", r.status_code == 200 and any(o.get("id") == org_id for o in r.json()), f"status={r.status_code} n={len(r.json())}", group=g)

    # Upgrade org to 'standard' plan so we can create 5 deps @ 15s interval
    r = req("PATCH", f"/v1/orgs/{org_id}", json={"plan": "standard"}, headers=bearer(owner_tok))
    check("PATCH org plan -> standard (for test)", r.status_code == 200 and r.json().get("plan") == "standard", f"status={r.status_code} body={r.text[:150]}", group=g)

    # Viewer cannot see the org (cross-tenant)
    r = req("GET", f"/v1/orgs/{org_id}", headers=bearer(viewer_tok))
    check("Viewer cannot access owner's org (404/403)", r.status_code in (403, 404), f"status={r.status_code}", group=g, severity="security")

    r = req("GET", f"/v1/orgs/{org_id}/members", headers=bearer(owner_tok))
    check("GET members", r.status_code == 200, f"status={r.status_code}", group=g)
    owner_membership = next((m for m in r.json() if m.get("role") == "owner"), None)
    check("Owner role present in members", bool(owner_membership), f"members={r.json()}", group=g)

    r = req("POST", f"/v1/orgs/{org_id}/members", json={"email": viewer_email, "role": "viewer"}, headers=bearer(owner_tok))
    check("Invite member (viewer)", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}", group=g)
    viewer_mid = r.json().get("id", "")

    r = req("POST", f"/v1/orgs/{org_id}/members", json={"email": member_email, "role": "member"}, headers=bearer(owner_tok))
    member_mid = r.json().get("id", "")
    check("Invite member (member)", r.status_code == 201, f"status={r.status_code}", group=g)

    r = req("PATCH", f"/v1/orgs/{org_id}/members/{viewer_mid}", json={"role": "admin"}, headers=bearer(owner_tok))
    check("PATCH member role -> admin", r.status_code == 200 and r.json().get("role") == "admin", f"status={r.status_code} body={r.text[:120]}", group=g)

    # Viewer (now admin) tries to access owner's org - should work after role change
    r = req("GET", f"/v1/orgs/{org_id}", headers=bearer(viewer_tok))
    check("Promoted member can access org", r.status_code == 200, f"status={r.status_code}", group=g)

    # Downgrade back to viewer and verify POST /dependencies is 403
    r = req("PATCH", f"/v1/orgs/{org_id}/members/{viewer_mid}", json={"role": "viewer"}, headers=bearer(owner_tok))
    check("PATCH member role -> viewer", r.status_code == 200, f"status={r.status_code}", group=g)
    r = req("POST", f"/v1/orgs/{org_id}/dependencies", json={
        "name": "should-fail", "endpoint_url": "https://api.github.com/zen",
        "check_interval_seconds": 300, "regions": ["us-east"]}, headers=bearer(viewer_tok))
    check("Viewer cannot POST dependencies (403)", r.status_code == 403, f"status={r.status_code} body={r.text[:150]}", group=g, severity="security")

    r = req("DELETE", f"/v1/orgs/{org_id}/members/{member_mid}", headers=bearer(owner_tok))
    check("DELETE member -> 204", r.status_code == 204, f"status={r.status_code}", group=g)
    r = req("GET", f"/v1/orgs/{org_id}/members", headers=bearer(owner_tok))
    check("Removed member no longer listed", all(m.get("id") != member_mid for m in r.json()), f"status={r.status_code}", group=g)

    # ─────────────────────────── DEPENDENCIES & CHECKS ───────────────────────────
    g = "Dependencies & Checks"
    torch_url = "https://files.pythonhosted.org/packages/9c/4f/3f1e0d9a4c8f4f4e1b0b3e9c1d2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a/torch-2.4.0-cp311-cp311-manylinux1_x86_64.whl"
    # use a real URL from PyPI metadata to be safe
    import urllib.request
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/torch/json", timeout=10) as u:
            meta = json.load(u)
        torch_url = next(
            f["url"] for f in meta["releases"].get("2.4.0", [])
            if f["packagetype"] == "bdist_wheel" and "cp311-cp311-manylinux1_x86_64" in f["filename"]
        )
    except Exception:
        pass

    deps = [
        {"name": "healthy-github", "endpoint_url": "https://api.github.com/zen", "method": "GET",
         "expected_status_codes": [200], "timeout_seconds": 10, "check_interval_seconds": 15,
         "regions": ["us-east", "eu-west"]},
        {"name": "unhealthy-404", "endpoint_url": f"https://api.github.com/repos/ReliaAstra/definitely-not-real-{uuid.uuid4().hex[:8]}",
         "method": "GET", "expected_status_codes": [200], "timeout_seconds": 10, "check_interval_seconds": 15,
         "regions": ["us-east", "eu-west"]},
        {"name": "slow-torch", "endpoint_url": torch_url, "method": "GET",
         "expected_status_codes": [200], "timeout_seconds": 3, "check_interval_seconds": 15,
         "regions": ["us-east", "eu-west"]},
        {"name": "redirect-301", "endpoint_url": "http://api.github.com/zen", "method": "GET",
         "expected_status_codes": [200], "timeout_seconds": 10, "check_interval_seconds": 15,
         "regions": ["us-east", "eu-west"]},
        {"name": "refused-ssrf", "endpoint_url": "http://localhost:9999/nonexistent", "method": "GET",
         "expected_status_codes": [200], "timeout_seconds": 5, "check_interval_seconds": 15,
         "regions": ["us-east", "eu-west"]},
    ]
    dep_ids: dict[str, str] = {}
    for d in deps:
        r = req("POST", f"/v1/orgs/{org_id}/dependencies", json=d, headers=bearer(owner_tok))
        ok = r.status_code == 201 and "id" in r.json()
        check(f"POST dependency {d['name']}", ok, f"status={r.status_code} body={r.text[:180]}", group=g)
        dep_ids[d["name"]] = r.json().get("id", "")

    r = req("GET", f"/v1/orgs/{org_id}/dependencies", headers=bearer(owner_tok))
    check("GET dependencies -> list of 5", r.status_code == 200 and len(r.json()) >= 5, f"status={r.status_code} n={len(r.json())}", group=g)

    # ─────────────────────────── WAIT FOR CHECKS ───────────────────────────
    print("\n[wait] waiting for scheduled checks to execute (max 180s)...", flush=True)
    deadline = time.time() + 180
    healthy_id = dep_ids.get("healthy-github", "")
    seen = 0
    while time.time() < deadline:
        r = req("GET", f"/v1/orgs/{org_id}/checks/recent?limit=50", headers=bearer(owner_tok))
        if r.status_code == 200 and r.json():
            seen = max(seen, len(r.json()))
        r2 = req("GET", f"/v1/orgs/{org_id}/dependencies/{healthy_id}/results?limit=5", headers=bearer(owner_tok)) if healthy_id else req("GET", f"/v1/orgs/{org_id}/dependencies", headers=bearer(owner_tok))
        if r2.status_code == 200 and (isinstance(r2.json(), list) and len(r2.json()) >= 1):
            break
        time.sleep(10)
    check("Checks executed within window (results appear)", seen >= 1, f"recent_count={seen}", group=g)

    r = req("GET", f"/v1/orgs/{org_id}/checks/recent?limit=50", headers=bearer(owner_tok))
    recent = r.json() if r.status_code == 200 else []
    check("GET /checks/recent -> list", r.status_code == 200 and isinstance(recent, list), f"status={r.status_code} n={len(recent)}", group=g)
    statuses = {}
    for cr in recent:
        statuses.setdefault(cr.get("dependency_id"), set()).add((cr.get("is_up"), cr.get("status_code")))

    # Per-dependency result verification
    for name, did in dep_ids.items():
        r = req("GET", f"/v1/orgs/{org_id}/dependencies/{did}/results?limit=10", headers=bearer(owner_tok))
        results = r.json() if r.status_code == 200 else []
        ok = r.status_code == 200 and len(results) >= 1
        sample = results[0] if results else {}
        check(f"GET results for {name}", ok, f"status={r.status_code} n={len(results)} first={ {k: sample.get(k) for k in ('is_up','status_code','latency_ms','error_message')} }", group=g)

    r = req("GET", f"/v1/orgs/{org_id}/dependencies/{healthy_id}/history?hours=1", headers=bearer(owner_tok))
    check("GET history (aggregation)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}", group=g)

    # Classify outcomes per dependency
    healthy_up = any(all((True, 200) == tuple(v) for v in vals) or any(v[0] is True for v in vals) for vals in [statuses.get(dep_ids.get("healthy-github",""), set())])
    unhealthy_down = any(v[0] is False for v in statuses.get(dep_ids.get("unhealthy-404",""), set()))
    slow_timeout = any(v[0] is False for v in statuses.get(dep_ids.get("slow-torch",""), set()))
    redirect_handled = any(v[0] is True for v in statuses.get(dep_ids.get("redirect-301",""), set()))
    refused_down = any(v[0] is False for v in statuses.get(dep_ids.get("refused-ssrf",""), set()))
    check("healthy dep classified UP", healthy_up, f"observed={statuses.get(dep_ids.get('healthy-github',''), set())}", group=g)
    check("unhealthy dep classified DOWN", unhealthy_down, f"observed={statuses.get(dep_ids.get('unhealthy-404',''), set())}", group=g)
    check("slow dep timed out (DOWN)", slow_timeout, f"observed={statuses.get(dep_ids.get('slow-torch',''), set())}", group=g)
    check("redirect dep followed redirect (UP)", redirect_handled, f"observed={statuses.get(dep_ids.get('redirect-301',''), set())}", group=g, severity="warn")
    check("refused dep DOWN (SSRF-blocked)", refused_down, f"observed={statuses.get(dep_ids.get('refused-ssrf',''), set())}", group=g)

    # ─────────────────────────── INCIDENTS ───────────────────────────
    g = "Incidents"
    time.sleep(5)
    r = req("GET", f"/v1/orgs/{org_id}/incidents", headers=bearer(owner_tok))
    incidents = r.json() if r.status_code == 200 else []
    check("GET incidents -> list", r.status_code == 200, f"status={r.status_code} n={len(incidents)}", group=g)
    unresolved = [i for i in incidents if i.get("status") != "resolved"]
    inc = unresolved[0] if unresolved else (incidents[0] if incidents else {})
    check("Incident created from unhealthy dep", bool(inc), f"incidents={[(i.get('status'), i.get('dependency_id'), i.get('severity')) for i in incidents]}", group=g, severity="warn")

    if inc:
        r = req("PATCH", f"/v1/orgs/{org_id}/incidents/{inc['id']}", json={"status": "resolved"}, headers=bearer(owner_tok))
        check("PATCH incident -> resolve", r.status_code == 200 and r.json().get("status") == "resolved", f"status={r.status_code} body={r.text[:160]}", group=g)

        r = req("POST", f"/v1/orgs/{org_id}/incidents/{inc['id']}/correlate", json={
            "correlated_dependency_id": dep_ids.get("slow-torch", ""),
            "correlation_confidence": 1.0, "correlation_method": "manual", "time_window_seconds": 300,
        }, headers=bearer(owner_tok))
        check("POST incident correlate", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}", group=g)

        r = req("GET", f"/v1/orgs/{org_id}/incidents/{inc['id']}/evidence", headers=bearer(owner_tok))
        check("GET incident evidence", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}", group=g)

    # ─────────────────────────── DASHBOARD ───────────────────────────
    g = "Dashboard"
    for path, name in [
        ("/summary", "summary KPIs"),
        ("/latency?hours=1", "latency timeseries"),
        ("/sla-degradation?period_days=7", "SLA degradation"),
        ("/dependency-health", "dependency health"),
        ("/incident-timeline", "incident timeline"),
        ("/vendor-status", "vendor status"),
    ]:
        r = req("GET", f"/v1/orgs/{org_id}/dashboard{path}", headers=bearer(owner_tok))
        ok = r.status_code == 200
        check(f"GET dashboard {name}", ok, f"status={r.status_code} body={r.text[:180]}", group=g)

    # ─────────────────────────── PUBLIC VENDORS ───────────────────────────
    g = "Public Vendors"
    r = req("GET", "/v1/public/vendors")
    check("GET /v1/public/vendors (pagination?)", r.status_code == 200, f"status={r.status_code} n={len(r.json()) if isinstance(r.json(), list) else 'dict'}", group=g)
    for path in ["/stripe", "/stripe/history", "/stripe/metrics", "/stripe/incidents"]:
        r = req("GET", f"/v1/public/vendors{path}")
        check(f"GET /v1/public/vendors{path}", r.status_code == 200, f"status={r.status_code} body={r.text[:150]}", group=g)

    # ─────────────────────────── NOTIFICATIONS ───────────────────────────
    g = "Notifications"
    r = req("POST", f"/v1/orgs/{org_id}/notifications/configs", json={
        "channel_type": "slack", "config": {"webhook_url": "https://hooks.slack.com/services/TEST/B0000/xxxx"}, "is_active": True,
    }, headers=bearer(owner_tok))
    check("POST notifications config (slack)", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}", group=g)
    cfg_id = r.json().get("id", "") if r.status_code == 201 else ""
    r = req("POST", f"/v1/orgs/{org_id}/notifications/test", json={"config_id": cfg_id}, headers=bearer(owner_tok))
    check("POST notifications test", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}", group=g)
    r = req("GET", f"/v1/orgs/{org_id}/notifications/configs", headers=bearer(owner_tok))
    check("GET notifications configs", r.status_code == 200, f"status={r.status_code} n={len(r.json())}", group=g)

    # ─────────────────────────── API KEYS ───────────────────────────
    g = "API Keys"
    r = req("POST", f"/v1/orgs/{org_id}/api-keys", json={"name": "ci-key", "scopes": ["read:checks", "write:dependencies", "read:incidents", "read:evidence"]}, headers=bearer(owner_tok))
    full_key = r.json().get("full_key", "") if r.status_code == 201 else ""
    key_id = r.json().get("id", "") if r.status_code == 201 else ""
    check("POST api-key -> full_key returned once", r.status_code == 201 and full_key.startswith("rel_"), f"status={r.status_code} full_key_present={bool(full_key)}", group=g)

    r = req("GET", f"/v1/orgs/{org_id}/api-keys", headers=bearer(owner_tok))
    listed = r.json() if r.status_code == 200 else []
    check("GET api-keys -> no full_key in list", r.status_code == 200 and all("full_key" not in k for k in listed), f"status={r.status_code}", group=g, severity="security")

    # Auth via API key on dependencies list (write scope covers deps)
    r = req("GET", f"/v1/orgs/{org_id}/dependencies", headers={"X-API-Key": full_key})
    check("API key auth (X-API-Key) works", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}", group=g)
    r = req("GET", f"/v1/orgs/{org_id}/dependencies", headers={"Authorization": f"ApiKey {full_key}"})
    check("API key auth (Authorization: ApiKey) works", r.status_code == 200, f"status={r.status_code}", group=g)

    # Cross-tenant: viewer's org (none) — API key must not grant other orgs
    r = req("POST", "/v1/orgs", json={"name": "viewer org"}, headers=bearer(viewer_tok))
    viewer_org = r.json().get("id", "") if r.status_code == 201 else ""
    r = req("GET", f"/v1/orgs/{viewer_org}/dependencies", headers={"X-API-Key": full_key})
    check("API key cannot access other orgs (403)", r.status_code in (403, 404), f"status={r.status_code} body={r.text[:100]}", group=g, severity="security")

    r = req("DELETE", f"/v1/orgs/{org_id}/api-keys/{key_id}", headers=bearer(owner_tok))
    check("DELETE api-key -> 204", r.status_code == 204, f"status={r.status_code}", group=g)
    r = req("GET", f"/v1/orgs/{org_id}/dependencies", headers={"X-API-Key": full_key})
    check("Revoked key rejected", r.status_code in (401, 403), f"status={r.status_code}", group=g, severity="security")

    # ─────────────────────────── BILLING ───────────────────────────
    g = "Billing"
    r = req("GET", f"/v1/orgs/{org_id}/billing/plan", headers=bearer(owner_tok))
    check("GET billing plan", r.status_code == 200 and "plan" in r.json(), f"status={r.status_code} body={r.text[:150]}", group=g)
    r = req("POST", f"/v1/orgs/{org_id}/billing/initialize", json={"plan": "starter", "email": email}, headers=bearer(owner_tok))
    ref = r.json().get("reference", "") if r.status_code in (200, 201) else ""
    check("POST billing initialize", r.status_code in (200, 201) and bool(ref), f"status={r.status_code} body={r.text[:200]}", group=g)
    r = req("POST", f"/v1/billing/verify?reference={ref}")
    check("POST billing verify", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}", group=g)

    # ─────────────────────────── EVIDENCE & VERIFICATION ───────────────────────────
    g = "Evidence & Verification"
    r = req("GET", f"/v1/orgs/{org_id}/evidence", headers=bearer(owner_tok))
    reports = r.json() if r.status_code == 200 else []
    check("GET evidence -> list reports", r.status_code == 200, f"status={r.status_code} n={len(reports)}", group=g)
    report = reports[0] if reports else {}
    report_id = report.get("id", "")
    if report_id:
        r = req("GET", f"/v1/orgs/{org_id}/evidence/{report_id}", headers=bearer(owner_tok))
        check("GET evidence report", r.status_code == 200, f"status={r.status_code} body_keys={list(r.json().keys())[:8] if r.status_code==200 else r.text[:100]}", group=g)
        r = req("POST", f"/v1/orgs/{org_id}/evidence/{report_id}/regenerate", headers=bearer(owner_tok))
        check("POST evidence regenerate", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}", group=g)
        vid = report.get("verification_id") or r.json().get("verification_id", "") if r.status_code in (200, 201) else ""
        if vid:
            r = req("GET", f"/v1/verify/{vid}")
            check("GET /v1/verify/{id} checksum verify", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}", group=g)

    # ─────────────────────────── SECURITY TESTS ───────────────────────────
    g = "Security"
    # Webhook signature enforcement
    r = req("POST", "/v1/billing/webhook", json={"event": "charge.success", "data": {"reference": "x"}})
    check("Webhook w/o signature rejected (401)", r.status_code in (401, 403), f"status={r.status_code} body={r.text[:120]}", group=g, severity="security")
    r = req("POST", "/v1/billing/webhook", json={"event": "charge.success", "data": {"reference": "x"}}, headers={"x-paystack-signature": "deadbeef"})
    check("Webhook w/ invalid signature rejected", r.status_code in (401, 403), f"status={r.status_code} body={r.text[:120]}", group=g, severity="security")

    # CORS preflight from evil origin
    r = req("OPTIONS", f"/v1/orgs/{org_id}/dependencies", headers={
        "Origin": "https://evil.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    cors_evil = r.headers.get("access-control-allow-origin", "")
    check("CORS blocks evil origin", cors_evil not in ("*", "https://evil.com"), f"ACAO='{cors_evil}' status={r.status_code}", group=g, severity="security")
    r = req("OPTIONS", f"/v1/orgs/{org_id}/dependencies", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    cors_ok = r.headers.get("access-control-allow-origin", "")
    check("CORS allows configured origin", cors_ok == "http://localhost:3000", f"ACAO='{cors_ok}'", group=g)

    # Idempotency: same key across two DIFFERENT users -> must NOT leak
    key = f"itest-{uuid.uuid4().hex}"
    r1 = req("POST", "/v1/orgs", json={"name": f"Idem A {uuid.uuid4().hex[:4]}"}, headers={**bearer(owner_tok), "Idempotency-Key": key})
    r2 = req("POST", "/v1/orgs", json={"name": f"Idem B {uuid.uuid4().hex[:4]}"}, headers={**bearer(viewer_tok), "Idempotency-Key": key})
    leak = r2.status_code in (200, 201) and bool(r2.json().get("id")) and r2.json().get("id") == r1.json().get("id")
    # EXPECTED FAILURE: cache key is `idempotency:{key}` with no user/org namespace.
    # Cross-tenant replay returns user A's cached response to user B.
    check("Idempotency key is user-scoped (no cross-tenant leak)",
          not leak and r1.status_code == 201 and r2.status_code == 201 and r2.json().get("id") != r1.json().get("id"),
          f"r1={r1.status_code} r2={r2.status_code} r1_org={r1.json().get('id')} r2_org={r2.json().get('id')} LEAK={leak}",
          group=g, severity="security")

    # ─────────────────────────── REPORT ───────────────────────────
    passed = sum(1 for x in RESULTS if x["pass"])
    total = len(RESULTS)
    print("\n" + "=" * 100)
    print(f"FUNCTIONAL SUITE SUMMARY: {passed}/{total} passed")
    print("=" * 100)
    for r_ in RESULTS:
        if not r_["pass"]:
            print(f"  FAIL [{r_['group']}] {r_['name']} :: {r_['detail']}")
    os.makedirs("audit/results", exist_ok=True)
    with open("audit/results/functional_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print("results -> audit/results/functional_results.json")


if __name__ == "__main__":
    main()
