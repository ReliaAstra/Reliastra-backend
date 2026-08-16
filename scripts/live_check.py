"""Live endpoint check for Reliastra backend — starts server inline, tests all endpoints."""
import subprocess
import time
import sys
import os
import signal
import json

# Ensure .env is used, not system env vars
for key in ["DATABASE_URL"]:
    if key in os.environ:
        del os.environ[key]

# Start uvicorn
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8111"],
    cwd="/home/z/my-project/reliastra-backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

# Wait for startup
for i in range(15):
    time.sleep(1)
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8111/health", timeout=2)
        print("Server is up!")
        break
    except Exception:
        if i == 14:
            print("Server failed to start. Output:")
            print(proc.stdout.read().decode())
            proc.kill()
            sys.exit(1)

# Now run httpx tests
import httpx
import asyncio

BASE = "http://127.0.0.1:8111"
results = []


async def test():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 1. Health
        r = await c.get("/health")
        results.append(("GET /health", r.status_code, r.json()))

        # 2. OpenAPI
        r = await c.get("/openapi.json")
        paths_count = len(r.json().get("paths", {}))
        results.append(("GET /openapi.json", r.status_code, {"total_paths": paths_count}))

        # 3. Register
        ts = int(time.time())
        email = f"livecheck{ts}@reliastra.com"
        r = await c.post("/v1/auth/register", json={
            "email": email, "password": "TestPass123!",
            "first_name": "Live", "last_name": "Check",
        })
        results.append(("POST /v1/auth/register", r.status_code, r.json()))
        register_data = r.json()

        # 4. Login
        r = await c.post("/v1/auth/login", json={
            "email": email, "password": "TestPass123!",
        })
        results.append(("POST /v1/auth/login", r.status_code, r.json()))
        login_data = r.json()
        token = login_data.get("access_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 5. Me
        r = await c.get("/v1/users/me", headers=headers)
        results.append(("GET /v1/users/me", r.status_code, r.json()))
        me_data = r.json()

        # Get org_id
        org_id = None
        if isinstance(me_data, dict):
            org_id = me_data.get("organization_id")
            if not org_id and me_data.get("organizations"):
                org_id = me_data["organizations"][0].get("id")

        # 6. Org detail
        if org_id:
            r = await c.get(f"/v1/orgs/{org_id}", headers=headers)
            results.append((f"GET /v1/orgs/{{id}}", r.status_code, r.json()))

        # 7. Dependencies CRUD
        if org_id:
            r = await c.post(f"/v1/orgs/{org_id}/dependencies", headers=headers, json={
                "name": "Stripe API", "endpoint_url": "https://api.stripe.com/v1", "check_type": "http",
            })
            results.append(("POST dependencies", r.status_code, r.json()))
            dep_data = r.json()
            dep_id = dep_data.get("id")
            if dep_id:
                r = await c.get(f"/v1/orgs/{org_id}/dependencies/{dep_id}", headers=headers)
                results.append(("GET dependency by id", r.status_code, r.json()))
                r = await c.get(f"/v1/orgs/{org_id}/dependencies", headers=headers)
                results.append(("GET dependencies list", r.status_code, {"count": len(r.json())}))

        # 8. Vendors
        r = await c.get("/v1/public/vendors")
        results.append(("GET /v1/public/vendors", r.status_code, r.json()))

        # 9. Refresh
        refresh = login_data.get("refresh_token")
        if refresh:
            r = await c.post("/v1/auth/refresh", json={"refresh_token": refresh})
            results.append(("POST /v1/auth/refresh", r.status_code, r.json()))

        # 10. Email verification
        r = await c.post("/v1/auth/send-verification", json={"email": email}, headers=headers)
        results.append(("POST /v1/auth/send-verification", r.status_code, r.json()))

        # 11. Forgot password
        r = await c.post("/v1/auth/forgot-password", json={"email": email})
        results.append(("POST /v1/auth/forgot-password", r.status_code, r.json()))

        # 12-20. Org-scoped endpoints
        endpoints_to_test = [
            ("dashboard/summary", "GET"),
            ("checks", "GET"),
            ("incidents", "GET"),
            ("notifications", "GET"),
            ("api-keys", "GET"),
            ("evidence", "GET"),
            ("billing/subscription", "GET"),
            ("agencies", "GET"),
            ("ai-providers", "GET"),
        ]
        if org_id:
            for ep, method in endpoints_to_test:
                try:
                    r = await c.get(f"/v1/orgs/{org_id}/{ep}", headers=headers)
                    results.append((f"GET {ep}", r.status_code, r.json()))
                except Exception as e:
                    results.append((f"GET {ep}", 0, {"error": str(e)[:100]}))

        # 21. Verification (public)
        r = await c.get("/v1/verify/test-id")
        results.append(("GET /v1/verify/test-id", r.status_code, r.json()))

        # 22. S3 Storage test
        try:
            os.chdir("/home/z/my-project/reliastra-backend")
            from app.infrastructure.storage import storage_client
            test_data = b"live check test data"
            storage_client.upload_bytes("live-check/test.txt", test_data)
            downloaded = storage_client.download_bytes("live-check/test.txt")
            match = downloaded == test_data
            results.append(("S3 upload/download", 200 if match else 500, {"match": match, "size": len(downloaded)}))
        except Exception as e:
            results.append(("S3 upload/download", 500, {"error": str(e)[:150]}))

    return results


try:
    results = asyncio.run(test())
except Exception as e:
    results.append(("UNHANDLED", 500, {"error": str(e)[:200]}))

# Kill server
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

# Print results
print(f"\n{'=' * 80}")
print(f"LIVE CHECK RESULTS: {len(results)} endpoints tested")
print(f"{'=' * 80}")
passed = 0
failed = 0
for name, status, data in results:
    s = "PASS" if 200 <= status < 400 else "FAIL"
    if s == "FAIL":
        failed += 1
    else:
        passed += 1
    data_str = json.dumps(data, default=str)[:150]
    print(f"  [{s}] {name} -> {status} | {data_str}")

print(f"\nSUMMARY: {passed} passed, {failed} failed out of {len(results)}")
sys.exit(1 if failed > 0 else 0)
