"""Reliastra production readiness — functional test suite (STEP 2).

Exercises the full API surface and records PASS/FAIL/SEVERITY per assertion.
Run:  .venv/bin/python audit/functional_suite.py
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
import uuid
from typing import Any

import httpx

BASE = os.environ.get("RELIASTRA_BASE", "http://127.0.0.1:8000")
RESULTS: list[dict[str, Any]] = []


def record(area: str, name: str, ok: bool, severity: str, detail: str = "") -> None:
    RESULTS.append(
        {"area": area, "test": name, "status": "PASS" if ok else "FAIL",
         "severity": "-" if ok else severity, "detail": detail[:300]}
    )
    flag = "PASS" if ok else f"FAIL[{severity}]"
    print(f"  {flag:12} {area} :: {name} {('- ' + detail[:160]) if detail else ''}")


class Client:
    def __init__(self) -> None:
        self.c = httpx.Client(base_url=BASE, timeout=60.0)
        self.access: str | None = None

    def h(self, extra: dict | None = None) -> dict:
        hd = {}
        if self.access:
            hd["Authorization"] = f"Bearer {self.access}"
        if extra:
            hd.update(extra)
        return hd

    def req(self, method: str, path: str, **kw) -> httpx.Response:
        kw.setdefault("headers", {})
        kw["headers"] = {**self.h(), **kw["headers"]}
        return self.c.request(method, path, **kw)


PSQL = ("/home/user/Reliastra-backend/.venv/lib/python3.11/site-packages/"
        "pgserver/pginstall/bin/psql")
DSN = "postgresql://postgres@127.0.0.1:5432/reliastra"


def set_plan(org_id: str, plan: str) -> None:
    import subprocess
    subprocess.run([PSQL, DSN, "-c",
                    f"UPDATE organizations SET plan='{plan}' WHERE id='{org_id}';"],
                   capture_output=True)


def main() -> int:
    cl = Client()
    suffix = secrets.token_hex(4)
    email = f"sre+{suffix}@reliastra-audit.dev"
    password = "AuditPassw0rd!2026"

    # ─────────────────────────── AUTH ────────────────────────────
    print("\n=== AUTH FLOW ===")
    r = cl.req("POST", "/v1/auth/register", json={
        "email": email, "password": password, "full_name": "Audit SRE"})
    ok = r.status_code in (200, 201)
    record("Auth", "POST /v1/auth/register", ok, "P0", f"{r.status_code} {r.text[:200]}")
    if not ok:
        print("FATAL: cannot register"); dump(); return 1
    body = r.json()
    token_fields = {"access_token", "refresh_token", "token_type"}
    record("Auth", "TokenResponse structure", token_fields.issubset(body.keys()),
           "P1", f"keys={sorted(body.keys())}")
    cl.access = body["access_token"]
    refresh = body["refresh_token"]

    r = cl.req("POST", "/v1/auth/login", json={"email": email, "password": password})
    record("Auth", "POST /v1/auth/login", r.status_code == 200, "P0", str(r.status_code))
    if r.status_code == 200:
        login_body = r.json()
        cl.access = login_body["access_token"]
        refresh = login_body["refresh_token"]

    r = cl.req("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    rot_ok = r.status_code == 200
    record("Auth", "POST /v1/auth/refresh", rot_ok, "P0", str(r.status_code))
    new_refresh = None
    if rot_ok:
        rb = r.json()
        new_refresh = rb.get("refresh_token")
        cl.access = rb["access_token"]
        record("Auth", "refresh token rotated (new != old)", new_refresh != refresh,
               "P0", "token reuse possible if equal")
        # old refresh must now be revoked
        r2 = cl.req("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
        record("Auth", "old refresh token revoked after rotation",
               r2.status_code in (401, 403), "P0",
               f"replay returned {r2.status_code}")

    # wrong password must fail
    r = cl.req("POST", "/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    record("Auth", "login rejects wrong password", r.status_code in (401, 400),
           "P0", str(r.status_code))

    # ───────────────────── ORGANIZATION & RBAC ─────────────────────
    print("\n=== ORG & RBAC ===")
    r = cl.req("POST", "/v1/orgs", json={"name": f"Audit Org {suffix}"})
    ok = r.status_code in (200, 201)
    record("Org", "POST /v1/orgs", ok, "P0", f"{r.status_code} {r.text[:200]}")
    if not ok:
        dump(); return 1
    org = r.json()
    org_id = org["id"]

    # Free plan caps deps at 3 / 60s interval. Upgrade the plan directly in the
    # database so the audit can exercise the full 5-dependency matrix.
    set_plan(org_id, "professional")

    r = cl.req("GET", "/v1/orgs")
    orgs = r.json() if r.status_code == 200 else []
    record("Org", "GET /v1/orgs", r.status_code == 200, "P1", str(r.status_code))
    if isinstance(orgs, list) and orgs:
        record("Org", "creator role == owner",
               any(o.get("role") == "owner" for o in orgs if isinstance(o, dict)),
               "P1", json.dumps(orgs[0])[:200])

    # second user to test RBAC
    viewer_email = f"viewer+{suffix}@reliastra-audit.dev"
    vc = Client()
    rv = vc.req("POST", "/v1/auth/register", json={
        "email": viewer_email, "password": password, "full_name": "Viewer User"})
    if rv.status_code in (200, 201):
        vc.access = rv.json()["access_token"]

    r = cl.req("POST", f"/v1/orgs/{org_id}/members",
               json={"email": viewer_email, "role": "viewer"})
    inv_ok = r.status_code in (200, 201)
    record("RBAC", "POST /v1/orgs/{id}/members (invite viewer)", inv_ok, "P1",
           f"{r.status_code} {r.text[:200]}")
    member_id = r.json().get("id") if inv_ok else None

    # viewer must NOT be able to create dependencies
    rdep = vc.req("POST", f"/v1/orgs/{org_id}/dependencies", json={
        "name": "viewer-should-fail", "endpoint_url": "https://httpbin.org/get",
        "method": "GET", "check_interval_seconds": 60})
    record("RBAC", "Viewer CANNOT POST dependencies (expect 403)",
           rdep.status_code == 403, "P0",
           f"got {rdep.status_code} — privilege escalation if 2xx")

    # viewer must not be able to read another org's data they aren't in
    rleak = vc.req("GET", f"/v1/orgs/{org_id}/dependencies")
    record("RBAC", "Viewer CAN read dependencies (read allowed)",
           rleak.status_code == 200, "P2", str(rleak.status_code))

    if member_id:
        r = cl.req("PATCH", f"/v1/orgs/{org_id}/members/{member_id}",
                   json={"role": "admin"})
        record("RBAC", "PATCH member role -> admin", r.status_code in (200, 204),
               "P1", f"{r.status_code} {r.text[:160]}")

    # cross-tenant isolation: outsider org
    oc = Client()
    out_email = f"outsider+{suffix}@reliastra-audit.dev"
    ro = oc.req("POST", "/v1/auth/register", json={
        "email": out_email, "password": password, "full_name": "Outsider"})
    if ro.status_code in (200, 201):
        oc.access = ro.json()["access_token"]
        rx = oc.req("GET", f"/v1/orgs/{org_id}/dependencies")
        record("RBAC", "Cross-tenant read blocked (expect 403/404)",
               rx.status_code in (403, 404), "P0",
               f"got {rx.status_code} — TENANT DATA LEAK if 200")
        rx2 = oc.req("GET", f"/v1/orgs/{org_id}/dashboard/summary")
        record("RBAC", "Cross-tenant dashboard blocked",
               rx2.status_code in (403, 404), "P0", f"got {rx2.status_code}")

    # ─────────────────── DEPENDENCIES & CHECKS ───────────────────
    print("\n=== DEPENDENCIES & CHECKS ===")
    deps_spec = [
        ("healthy", "https://httpbin.org/get", [200]),
        ("unhealthy-500", "https://httpbin.org/status/500", [200]),
        ("slow-delay15", "https://httpbin.org/delay/15", [200]),
        ("redirect-chain", "https://httpbin.org/redirect/3", [200]),
        ("conn-refused", "http://localhost:9999/nonexistent", [200]),
    ]
    dep_ids: dict[str, str] = {}
    for name, url, codes in deps_spec:
        r = cl.req("POST", f"/v1/orgs/{org_id}/dependencies", json={
            "name": f"{name}-{suffix}", "endpoint_url": url, "method": "GET",
            "check_interval_seconds": 60, "timeout_seconds": 10,
            "expected_status_codes": codes, "regions": ["us-east", "eu-west"]})
        ok = r.status_code in (200, 201)
        record("Dependencies", f"POST dependency [{name}]", ok,
               "P0" if name == "healthy" else "P1",
               f"{r.status_code} {r.text[:200]}")
        if ok:
            dep_ids[name] = r.json()["id"]

    record("Security", "SSRF: localhost dependency accepted at create time",
           "conn-refused" not in dep_ids, "P1",
           "create-time SSRF validation absent; only enforced at probe time"
           if "conn-refused" in dep_ids else "rejected at create")

    r = cl.req("GET", f"/v1/orgs/{org_id}/dependencies")
    record("Dependencies", "GET dependencies list", r.status_code == 200, "P1",
           f"{r.status_code} count={len(r.json()) if r.status_code==200 else 'n/a'}")

    # redirect behaviour: httpx does NOT follow redirects by default
    print("\n  [waiting up to 150s for scheduler to execute checks...]")
    healthy_id = dep_ids.get("healthy")
    results_seen = 0
    deadline = time.time() + 150
    while time.time() < deadline:
        if healthy_id:
            rr = cl.req("GET", f"/v1/orgs/{org_id}/dependencies/{healthy_id}/results")
            if rr.status_code == 200 and len(rr.json()) > 0:
                results_seen = len(rr.json())
                break
        time.sleep(10)
    record("Checks", "Scheduler executed checks within 150s", results_seen > 0,
           "P0", f"results for healthy dep = {results_seen}")

    if healthy_id:
        r = cl.req("GET", f"/v1/orgs/{org_id}/dependencies/{healthy_id}/results")
        record("Checks", "GET dependency results", r.status_code == 200, "P1",
               str(r.status_code))
        r = cl.req("GET", f"/v1/orgs/{org_id}/dependencies/{healthy_id}/history")
        record("Checks", "GET dependency history (aggregation)",
               r.status_code == 200, "P1", f"{r.status_code} {r.text[:160]}")

    r = cl.req("GET", f"/v1/orgs/{org_id}/checks/recent")
    recent = r.json() if r.status_code == 200 else []
    record("Checks", "GET /checks/recent", r.status_code == 200, "P1",
           f"{r.status_code} n={len(recent) if isinstance(recent,list) else '?'}")

    # redirect dependency should be marked down (httpx no-follow default)
    rd = dep_ids.get("redirect-chain")
    if rd:
        rr = cl.req("GET", f"/v1/orgs/{org_id}/dependencies/{rd}/results")
        if rr.status_code == 200 and rr.json():
            codes = [x.get("status_code") for x in rr.json()]
            record("Checks", "Redirect chain NOT followed (302 recorded as down)",
                   any(c in (301, 302, 307, 308) for c in codes if c), "P1",
                   f"status codes observed={codes[:5]}")

    # slow dependency should time out
    sd = dep_ids.get("slow-delay15")
    if sd:
        rr = cl.req("GET", f"/v1/orgs/{org_id}/dependencies/{sd}/results")
        if rr.status_code == 200 and rr.json():
            errs = [x.get("error_message") for x in rr.json()]
            record("Checks", "Slow endpoint times out at timeout_seconds",
                   any(e and ("timeout" in e.lower() or "timed out" in e.lower())
                       for e in errs), "P1", f"errors={[e for e in errs[:3]]}")

    # ───────────────────────── INCIDENTS ─────────────────────────
    print("\n=== INCIDENTS ===")
    r = cl.req("GET", f"/v1/orgs/{org_id}/incidents")
    inc_ok = r.status_code == 200
    incidents = r.json() if inc_ok else []
    record("Incidents", "GET incidents", inc_ok, "P1",
           f"{r.status_code} n={len(incidents) if isinstance(incidents,list) else '?'}")
    record("Incidents", "500-status dependency produced an incident",
           bool(incidents), "P0",
           f"incident count={len(incidents) if isinstance(incidents,list) else 0}; "
           "quorum requires 2 regions failing within 60s window")

    inc_id = incidents[0]["id"] if incidents else None
    if inc_id:
        r = cl.req("GET", f"/v1/orgs/{org_id}/incidents/{inc_id}/evidence")
        record("Incidents", "GET incident evidence", r.status_code in (200, 404),
               "P2", f"{r.status_code} {r.text[:160]}")
        other = [v for k, v in dep_ids.items() if k != "unhealthy-500"]
        if other:
            r = cl.req("POST", f"/v1/orgs/{org_id}/incidents/{inc_id}/correlate",
                       json={"dependency_id": other[0]})
            record("Incidents", "POST incident correlate",
                   r.status_code in (200, 201), "P2",
                   f"{r.status_code} {r.text[:160]}")
        r = cl.req("PATCH", f"/v1/orgs/{org_id}/incidents/{inc_id}",
                   json={"status": "resolved"})
        record("Incidents", "PATCH resolve incident", r.status_code in (200, 204),
               "P1", f"{r.status_code} {r.text[:160]}")

    # ───────────────────────── DASHBOARD ─────────────────────────
    print("\n=== DASHBOARD ===")
    dash = [
        ("summary", f"/v1/orgs/{org_id}/dashboard/summary"),
        ("latency?hours=1", f"/v1/orgs/{org_id}/dashboard/latency?hours=1"),
        ("sla-degradation", f"/v1/orgs/{org_id}/dashboard/sla-degradation?period_days=7"),
        ("dependency-health", f"/v1/orgs/{org_id}/dashboard/dependency-health"),
        ("incident-timeline", f"/v1/orgs/{org_id}/dashboard/incident-timeline"),
        ("vendor-status", f"/v1/orgs/{org_id}/dashboard/vendor-status"),
    ]
    for label, path in dash:
        t0 = time.time()
        r = cl.req("GET", path)
        dt = (time.time() - t0) * 1000
        record("Dashboard", f"GET {label}", r.status_code == 200, "P1",
               f"{r.status_code} {dt:.0f}ms {r.text[:120]}")

    # unbounded range check
    t0 = time.time()
    r = cl.req("GET", f"/v1/orgs/{org_id}/dashboard/latency?hours=2160")
    dt = (time.time() - t0) * 1000
    record("Dashboard", "latency?hours=2160 (90d max) accepted",
           r.status_code == 200, "P1", f"{r.status_code} {dt:.0f}ms")
    r = cl.req("GET", f"/v1/orgs/{org_id}/dashboard/latency?hours=999999")
    record("Dashboard", "latency rejects absurd range (expect 422)",
           r.status_code == 422, "P2",
           f"got {r.status_code} — unbounded scan risk if 200")

    # ─────────────────────── PUBLIC VENDORS ───────────────────────
    print("\n=== PUBLIC VENDORS ===")
    pub = httpx.Client(base_url=BASE, timeout=60.0)
    r = pub.get("/v1/public/vendors")
    vend_ok = r.status_code == 200
    vbody = r.json() if vend_ok else None
    record("PublicVendors", "GET /v1/public/vendors", vend_ok, "P1", str(r.status_code))
    paginated = isinstance(vbody, dict) and any(
        k in vbody for k in ("items", "total", "page", "next"))
    record("PublicVendors", "vendor list is paginated", paginated, "P1",
           f"returned {type(vbody).__name__} — unbounded list if array")
    for sub in ("", "/history", "/metrics", "/incidents"):
        r = pub.get(f"/v1/public/vendors/stripe{sub}")
        record("PublicVendors", f"GET /public/vendors/stripe{sub or ' (detail)'}",
               r.status_code in (200, 404), "P2", f"{r.status_code} {r.text[:120]}")

    # ─────────────────────── NOTIFICATIONS ───────────────────────
    print("\n=== NOTIFICATIONS ===")
    r = cl.req("POST", f"/v1/orgs/{org_id}/notifications/configs", json={
        "channel_type": "slack",
        "config": {"webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX"},
        "is_active": True})
    cfg_id = r.json().get("id") if r.status_code in (200, 201) else None
    record("Notifications", "POST notification config", r.status_code in (200, 201),
           "P2", f"{r.status_code} {r.text[:200]}")
    r = cl.req("POST", f"/v1/orgs/{org_id}/notifications/test",
               json={"config_id": cfg_id} if cfg_id else {})
    record("Notifications", "POST notifications/test",
           r.status_code in (200, 201, 202, 204), "P2",
           f"{r.status_code} {r.text[:200]}")

    # ───────────────────────── API KEYS ─────────────────────────
    print("\n=== API KEYS ===")
    r = cl.req("POST", f"/v1/orgs/{org_id}/api-keys", json={"name": "audit-key"})
    key_ok = r.status_code in (200, 201)
    record("ApiKeys", "POST api-keys", key_ok, "P1", f"{r.status_code} {r.text[:200]}")
    full_key = None
    key_id = None
    if key_ok:
        kb = r.json()
        full_key = kb.get("full_key") or kb.get("key") or kb.get("api_key")
        key_id = kb.get("id")
        record("ApiKeys", "full_key returned once on create", bool(full_key), "P1",
               f"keys={sorted(kb.keys())}")
    r = cl.req("GET", f"/v1/orgs/{org_id}/api-keys")
    if r.status_code == 200:
        listed = r.json()
        leaked = any(
            (i.get("full_key") or i.get("key")) for i in listed if isinstance(i, dict))
        record("ApiKeys", "list does NOT expose full_key", not leaked, "P0",
               "SECRET LEAK in list endpoint" if leaked else "")
    if full_key:
        ak = httpx.Client(base_url=BASE, timeout=60.0)
        r = ak.get(f"/v1/orgs/{org_id}/dependencies",
                   headers={"Authorization": f"ApiKey {full_key}"})
        record("ApiKeys", "ApiKey auth scheme works", r.status_code == 200, "P1",
               f"{r.status_code} {r.text[:160]}")
        r = ak.get(f"/v1/orgs/{org_id}/dependencies",
                   headers={"X-API-Key": full_key})
        record("ApiKeys", "X-API-Key header accepted", r.status_code == 200, "P2",
               str(r.status_code))
    if key_id:
        r = cl.req("DELETE", f"/v1/orgs/{org_id}/api-keys/{key_id}")
        record("ApiKeys", "DELETE api-key (revoke)", r.status_code in (200, 204),
               "P1", str(r.status_code))
        if full_key:
            time.sleep(1)
            r = httpx.get(f"{BASE}/v1/orgs/{org_id}/dependencies",
                          headers={"Authorization": f"ApiKey {full_key}"}, timeout=30)
            record("ApiKeys", "revoked key rejected", r.status_code in (401, 403),
                   "P0", f"got {r.status_code} — revocation broken if 200")

    # ────────────────────────── BILLING ──────────────────────────
    print("\n=== BILLING ===")
    r = cl.req("GET", f"/v1/orgs/{org_id}/billing/plan")
    record("Billing", "GET billing/plan", r.status_code == 200, "P1",
           f"{r.status_code} {r.text[:200]}")
    r = cl.req("POST", f"/v1/orgs/{org_id}/billing/initialize",
               json={"plan": "starter", "email": email})
    record("Billing", "POST billing/initialize",
           r.status_code in (200, 201, 400, 422, 502, 503), "P2",
           f"{r.status_code} {r.text[:200]}")
    r = cl.req("POST", "/v1/billing/verify?reference=audit-fake-ref")
    record("Billing", "POST billing/verify (bad ref rejected)",
           r.status_code != 200, "P1", f"{r.status_code} {r.text[:200]}")

    # ───────────────────── EVIDENCE & VERIFY ─────────────────────
    print("\n=== EVIDENCE ===")
    r = cl.req("GET", f"/v1/orgs/{org_id}/evidence")
    ev_ok = r.status_code == 200
    reports = r.json() if ev_ok else []
    record("Evidence", "GET evidence list", ev_ok, "P1",
           f"{r.status_code} n={len(reports) if isinstance(reports,list) else '?'}")
    if isinstance(reports, list) and reports:
        rid = reports[0]["id"]
        r = cl.req("GET", f"/v1/orgs/{org_id}/evidence/{rid}")
        record("Evidence", "GET evidence report", r.status_code == 200, "P2",
               str(r.status_code))
        r = cl.req("POST", f"/v1/orgs/{org_id}/evidence/{rid}/regenerate")
        record("Evidence", "POST evidence regenerate",
               r.status_code in (200, 201, 202), "P2", f"{r.status_code} {r.text[:160]}")
        vid = (reports[0].get("verification_id") or reports[0].get("id"))
        r = pub.get(f"/v1/verify/{vid}")
        record("Evidence", "GET /v1/verify/{id}", r.status_code in (200, 404), "P1",
               f"{r.status_code} {r.text[:160]}")
    else:
        record("Evidence", "evidence auto-generated for incident", False, "P2",
               "no evidence reports were produced by the incident lifecycle")

    r = pub.get(f"/v1/verify/{uuid.uuid4()}")
    record("Evidence", "verify unknown id returns 404", r.status_code == 404, "P2",
           str(r.status_code))

    # ─────────────────────── LOGOUT (last) ───────────────────────
    print("\n=== LOGOUT ===")
    tok = new_refresh or refresh
    r = cl.req("POST", "/v1/auth/logout", json={"refresh_token": tok})
    record("Auth", "POST /v1/auth/logout returns 204",
           r.status_code == 204, "P2", f"got {r.status_code}")
    r = cl.req("POST", "/v1/auth/refresh", json={"refresh_token": tok})
    record("Auth", "refresh token revoked after logout",
           r.status_code in (401, 403), "P0",
           f"got {r.status_code} — session not terminated if 200")

    dump()
    return 0


def dump() -> None:
    os.makedirs("audit/out", exist_ok=True)
    with open("audit/out/functional_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)
    p = sum(1 for r in RESULTS if r["status"] == "PASS")
    print(f"\n===== FUNCTIONAL: {p}/{len(RESULTS)} passed, "
          f"{len(RESULTS)-p} failed =====")


if __name__ == "__main__":
    sys.exit(main())
