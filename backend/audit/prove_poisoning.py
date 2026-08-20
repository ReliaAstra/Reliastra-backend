"""Prove that the quorum race PERMANENTLY poisons a dependency.

Once two concurrent regions both insert an open incident for the same
dependency, IncidentRepository.get_open_for_dependency() uses
scalar_one_or_none(), which raises MultipleResultsFound forever after.
Every subsequent check for that dependency then dies — monitoring silently
stops for that customer AND the incident can never auto-resolve.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE = "http://127.0.0.1:8000"
PSQL = ("/home/user/Reliastra-backend/.venv/lib/python3.11/site-packages/"
        "pgserver/pginstall/bin/psql")
DSN = "postgresql://postgres@127.0.0.1:5432/reliastra"
TARGET_FAIL = "https://api.github.com/nope-does-not-exist-404"


def sql(q: str) -> str:
    r = subprocess.run([PSQL, DSN, "-t", "-A", "-c", q],
                       capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


async def main() -> None:
    import secrets

    from app.db.session import get_session_maker
    from app.modules.checks.service import check_service

    s = secrets.token_hex(4)
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/v1/auth/register", json={
        "email": f"poison+{s}@reliastra-audit.dev",
        "password": "AuditPassw0rd!2026", "full_name": "Poison"})
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    org_id = c.post("/v1/orgs", json={"name": f"Poison {s}"}, headers=h).json()["id"]
    sql(f"UPDATE organizations SET plan='agency' WHERE id='{org_id}';")
    dep_id = c.post(f"/v1/orgs/{org_id}/dependencies", json={
        "name": "poison-dep", "endpoint_url": TARGET_FAIL, "method": "GET",
        "check_interval_seconds": 3600, "timeout_seconds": 10,
        "expected_status_codes": [200],
        "regions": ["us-east", "eu-west"]}, headers=h).json()["id"]

    sm = get_session_maker()

    async def probe(region: str) -> str:
        async with sm() as sess:
            try:
                await check_service.execute_check(sess, uuid.UUID(dep_id), region)
                await sess.commit()
                return "ok"
            except Exception as e:
                await sess.rollback()
                return f"{type(e).__name__}: {e}"

    print("PHASE 1 — concurrent two-region failure (the race):")
    out = await asyncio.gather(probe("us-east"), probe("eu-west"))
    print(f"   us-east: {out[0]}")
    print(f"   eu-west: {out[1]}")
    n = sql(f"SELECT count(*) FROM incidents WHERE dependency_id='{dep_id}' "
            "AND status='open';")
    print(f"   open incidents now: {n}  (correct = 1)")

    print("\nPHASE 2 — subsequent checks on the SAME dependency:")
    dead = 0
    for i in range(4):
        res = await probe("us-east")
        print(f"   check #{i+1}: {res}")
        if res != "ok":
            dead += 1

    rows = sql(f"SELECT count(*) FROM check_results WHERE dependency_id='{dep_id}';")
    print(f"\n   check_results ever written for this dependency: {rows}")
    print(f"   failed subsequent checks: {dead}/4")

    print("\nPHASE 3 — can the incident still auto-resolve? "
          "(simulate vendor recovery)")
    sql(f"UPDATE dependencies SET endpoint_url='https://api.github.com/status' "
        f"WHERE id='{dep_id}';")
    res = await probe("us-east")
    print(f"   recovery check: {res}")
    still_open = sql(f"SELECT count(*) FROM incidents WHERE dependency_id="
                     f"'{dep_id}' AND status='open';")
    print(f"   open incidents after recovery: {still_open}")

    print("\nVERDICT:")
    if dead >= 3:
        print("   CONFIRMED PERMANENT POISONING — the dependency is bricked.")
        print("   Monitoring for this customer endpoint stops forever, the")
        print("   incident can never auto-resolve, and only manual SQL fixes it.")
    else:
        print("   Not reproduced in this run.")


if __name__ == "__main__":
    asyncio.run(main())
