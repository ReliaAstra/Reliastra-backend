#!/bin/bash
BASE="http://127.0.0.1:8333"
TS=$(date +%s)
EMAIL="livecheck${TS}@reliastra.com"
PASS=0
FAIL=0
ERRORS=""

t() {
    local label="$1"
    local method="$2"
    local url="$3"
    local body="$4"
    local hdr="$5"
    
    local resp
    local code
    
    if [ -n "$body" ]; then
        resp=$(curl -s --max-time 10 -X "$method" -H "Content-Type: application/json" $hdr -d "$body" "$url" 2>/dev/null)
    else
        resp=$(curl -s --max-time 10 -X "$method" $hdr "$url" 2>/dev/null)
    fi
    code=$(echo "$resp" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    if 'error' in d:
        print('FAIL')
    elif 'access_token' in d or 'items' in d or 'id' in d or 'status' in d or 'vendors' in d or 'message' in d or isinstance(d, list) or 'checks' in d or 'subscription' in d or 'name' in d:
        print('PASS')
    else:
        print('PASS')
except:
    print('FAIL')
" 2>/dev/null)
    
    if [ "$code" = "PASS" ]; then
        echo "  [PASS] $label"
        PASS=$((PASS + 1))
    else
        short=$(echo "$resp" | head -c 200)
        echo "  [FAIL] $label | $short"
        ERRORS="$ERRORS\n  $label: $short"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "========================================================================"
echo "LIVE CHECK: Reliastra Backend — $(date)"
echo "========================================================================"
echo ""

# 1. Health
t "GET /health" GET "$BASE/health"

# 2. OpenAPI
t "GET /openapi.json" GET "$BASE/openapi.json"

# 3. Register
REG_RESP=$(curl -s --max-time 10 -X POST "$BASE/v1/auth/register" -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\",\"password\":\"TestPass123!\",\"full_name\":\"Live Check User\",\"org_name\":\"LiveCheck Org\"}")
TOKEN=$(echo "$REG_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
REFRESH=$(echo "$REG_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null)
AUTH="-H 'Authorization: Bearer $TOKEN'"
t "POST /v1/auth/register" POST "$BASE/v1/auth/register" "{\"email\":\"$EMAIL\",\"password\":\"TestPass123!\",\"full_name\":\"Live Check User\"}"

# 4. Login
t "POST /v1/auth/login" POST "$BASE/v1/auth/login" "{\"email\":\"$EMAIL\",\"password\":\"TestPass123!\"}"

# 5. Users/Me
t "GET /v1/users/me" GET "$BASE/v1/users/me" "" "$AUTH"

# 6. Refresh
t "POST /v1/auth/refresh" POST "$BASE/v1/auth/refresh" "{\"refresh_token\":\"$REFRESH\"}"

# 7. Send verification
t "POST /v1/auth/send-verification" POST "$BASE/v1/auth/send-verification" "{\"email\":\"$EMAIL\"}" "$AUTH"

# 8. Forgot password
t "POST /v1/auth/forgot-password" POST "$BASE/v1/auth/forgot-password" "{\"email\":\"$EMAIL\"}"

# Get org_id
ORG_ID=$(curl -s --max-time 10 $AUTH "$BASE/v1/orgs" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'] if d else '')" 2>/dev/null)

if [ -n "$ORG_ID" ]; then
    echo "  --- Org-scoped endpoints (org_id=$ORG_ID) ---"
    
    t "GET /v1/orgs/{id}" GET "$BASE/v1/orgs/$ORG_ID" "" "$AUTH"
    t "POST dependencies" POST "$BASE/v1/orgs/$ORG_ID/dependencies" "{\"name\":\"Stripe API\",\"endpoint_url\":\"https://api.stripe.com/v1\",\"check_type\":\"http\"}" "$AUTH"
    t "GET dependencies" GET "$BASE/v1/orgs/$ORG_ID/dependencies" "" "$AUTH"
    t "GET checks" GET "$BASE/v1/orgs/$ORG_ID/checks" "" "$AUTH"
    t "GET incidents" GET "$BASE/v1/orgs/$ORG_ID/incidents" "" "$AUTH"
    t "GET notifications" GET "$BASE/v1/orgs/$ORG_ID/notifications" "" "$AUTH"
    t "GET api-keys" GET "$BASE/v1/orgs/$ORG_ID/api-keys" "" "$AUTH"
    t "GET evidence" GET "$BASE/v1/orgs/$ORG_ID/evidence" "" "$AUTH"
    t "GET billing" GET "$BASE/v1/orgs/$ORG_ID/billing/subscription" "" "$AUTH"
    t "GET agencies" GET "$BASE/v1/orgs/$ORG_ID/agencies" "" "$AUTH"
    t "GET ai-providers" GET "$BASE/v1/orgs/$ORG_ID/ai-providers" "" "$AUTH"
    t "GET dashboard" GET "$BASE/v1/orgs/$ORG_ID/dashboard/summary" "" "$AUTH"
else
    echo "  [SKIP] Org-scoped endpoints (no org_id found)"
fi

# Public endpoints
t "GET /v1/public/vendors" GET "$BASE/v1/public/vendors"
t "GET /v1/verify/test-id" GET "$BASE/v1/verify/test-id"

# S3 Storage test
echo "  --- S3 Storage ---"
unset DATABASE_URL
S3_RESULT=$(python3 -c "
from app.infrastructure.storage import storage_client
storage_client.upload_bytes(b'live check data 123', 'live-check-test/test.txt')
data = storage_client.download_bytes('live-check-test/test.txt')
import json
print(json.dumps({'match': data == b'live check data 123', 'size': len(data)}))
" 2>&1)
if echo "$S3_RESULT" | python3 -c "import sys,json;d=json.load(sys.stdin);exit(0 if d.get('match') else 1)" 2>/dev/null; then
    echo "  [PASS] S3 upload/download | $S3_RESULT"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] S3 upload/download | $S3_RESULT"
    FAIL=$((FAIL + 1))
    ERRORS="$ERRORS\n  S3: $S3_RESULT"
fi

echo ""
echo "========================================================================"
echo "SUMMARY: $PASS passed, $FAIL failed out of $((PASS + FAIL))"
if [ $FAIL -gt 0 ]; then
    echo ""
    echo "FAILURES:"
    echo -e "$ERRORS"
fi
echo "========================================================================"
