"""Characterise the quorum race across many independent trials.

Each trial: one fresh dependency, two regions failing concurrently.
Correct behaviour = exactly 1 open incident, every time.
Records the distribution of outcomes and whether the dependency gets
permanently bricked by MultipleResultsFound.
"""
from __future__ import annotations

import asyncio
import collections
import json
import os
import secrets
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
TRIALS = 15


def sql(q: str) -> str:
    r = subprocess.run([PSQL, DSN, "-t", "-A", "-c", q],
                       capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


async def main() -> None:
    from app.db.session import get_session_maker
    from app.modules.checks.service import check_service

    s = secrets.token_hex(4)
    c = httpx.Client(base_url=BASE, timeout=60)
    tok = c.post("/v1/auth/register", json={
        "email": f"quorum+{s}@reliastra-audit.dev",
        "password": "AuditPassw0rd!2026",
        "full_name": "Quorum"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    org_id = c.post("/v1/orgs", json={"name": f"Quorum {s}"},
                    headers=h).json()["id"]
    sql(f"UPDATE organizations SET plan='agency' WHERE id='{org_id}';")

    sm = get_session_maker()

    async def probe(dep_id: str, region: str) -> str:
        async with sm() as sess:
            try:
                await check_service.execute_check(sess, uuid.UUID(dep_id), region)
                await sess.commit()
                return "ok"
            except Exception as e:
                await sess.rollback()
                return f"{type(e).__name__}"

    outcomes: collections.Counter = collections.Counter()
    bricked = 0
    details = []

    for t in range(TRIALS):
        dep_id = c.post(f"/v1/orgs/{org_id}/dependencies", json={
            "name": f"q-{t}-{secrets.token_hex(2)}",
            "endpoint_url": TARGET_FAIL, "method": "GET",
            "check_interval_seconds": 3600, "timeout_seconds": 10,
            "expected_status_codes": [200],
            "regions": ["us-east", "eu-west"]}, headers=h).json()["id"]

        r1, r2 = await asyncio.gather(probe(dep_id, "us-east"),
                                      probe(dep_id, "eu-west"))
        n_open = int(sql("SELECT count(*) FROM incidents WHERE dependency_id="
                         f"'{dep_id}' AND status='open';") or 0)

        # Is the dependency now permanently broken?
        follow = await probe(dep_id, "us-east")
        if follow != "ok":
            bricked += 1

        if n_open == 1:
            label = "correct (1 incident)"
        elif n_open == 0:
            label = "MISSED incident (0)"
        else:
            label = f"DUPLICATE incidents ({n_open})"
        outcomes[label] += 1
        details.append({"trial": t, "region_results": [r1, r2],
                        "open_incidents": n_open,
                        "followup_check": follow})
        print(f"  trial {t:2}: regions=({r1},{r2}) open_incidents={n_open} "
              f"followup={follow}  -> {label}")

    print("\n=== QUORUM RACE OUTCOME DISTRIBUTION "
          f"({TRIALS} independent trials) ===")
    for k, v in outcomes.most_common():
        print(f"  {v:3}/{TRIALS}  {k}")
    print(f"  {bricked:3}/{TRIALS}  dependencies permanently bricked "
          f"(MultipleResultsFound on every later check)")

    correct = outcomes.get("correct (1 incident)", 0)
    print(f"\n  CORRECTNESS RATE: {correct}/{TRIALS} "
          f"({correct/TRIALS*100:.0f}%)")

    os.makedirs("audit/out", exist_ok=True)
    with open("audit/out/quorum_trials.json", "w") as f:
        json.dump({"trials": TRIALS, "outcomes": dict(outcomes),
                   "bricked": bricked, "correctness_rate": correct / TRIALS,
                   "details": details}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
