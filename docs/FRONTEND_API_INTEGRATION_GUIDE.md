# Reliastra Frontend & Dashboard Integration Guide

This guide provides frontend and dashboard developers with complete integration specifications, TypeScript type definitions, exact request/response payloads, and UI patterns for integrating with the **Reliastra External Dependency Intelligence Backend**.

---

## 1. Core Integration Concepts

- **Base URL**: All REST endpoints are prefixed with `/v1`.
  - Local development: `http://localhost:8000/v1`
  - OpenAPI Spec: `http://localhost:8000/openapi.json` (exported locally to `docs/openapi.json`)
  - Swagger UI: `http://localhost:8000/docs`
- **CORS**: The backend is configured to allow `http://localhost:3000`, `http://localhost:5173`, and `http://127.0.0.1:3000`.
- **Idempotency Header**: For mutation requests (`POST`, `PUT`, `DELETE`), include a unique UUID in the `Idempotency-Key` HTTP header. The backend caches the response in Redis for 24 hours to prevent duplicate submissions on network retries.
- **Error Responses**: Standardized JSON error envelope across all endpoints:
  ```json
  {
    "error": "validation_error",
    "message": "Input validation failed",
    "details": {
      "field": ["error description"]
    }
  }
  ```

---

## 2. Authentication & Session Lifecycle

The platform supports **Dual Authentication**:
1. **JWT Access & Refresh Tokens** for human users in browser dashboards.
2. **API Keys** (`rel_...`) for automated CI/CD and script integrations.

### 2.1 HTTP Authentication Headers
- For user sessions:  
  `Authorization: Bearer <access_token>`
- For API key integrations:  
  `Authorization: ApiKey rel_xxxxxxxxxxxx...`

### 2.2 Endpoints & Payloads

#### **POST /v1/auth/register**
Creates a new user account.
```json
// Request Body
{
  "email": "admin@reliastra.dev",
  "password": "SecurePassword123!",
  "full_name": "Jane Doe"
}

// Response (201 Created)
{
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "admin@reliastra.dev",
    "full_name": "Jane Doe",
    "is_active": true
  },
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### **POST /v1/auth/login**
```json
// Request Body
{
  "email": "admin@reliastra.dev",
  "password": "SecurePassword123!"
}

// Response (200 OK) -> Same TokenResponse structure as register
```

#### **POST /v1/auth/refresh**
Rotate tokens transparently when an access token expires (`401 Unauthorized`).
```json
// Request Body
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn..."
}

// Response (200 OK) -> Returns a new TokenResponse
```

#### **POST /v1/auth/logout**
Revokes the refresh token in Redis and postgres.
```json
// Request Body
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn..."
}
// Response (200 OK)
{
  "message": "Successfully logged out"
}
```

---

## 3. Multi-Tenancy & Organization Context

Every operational endpoint requires an `{org_id}` path parameter. When a user logs in, the dashboard should load `/v1/users/me` and `/v1/orgs` to populate the workspace switcher.

### 3.1 Get Current User (`GET /v1/users/me`)
```json
// Response (200 OK)
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "admin@reliastra.dev",
  "full_name": "Jane Doe",
  "is_active": true
}
```

### 3.2 List User Organizations (`GET /v1/orgs`)
Returns all organizations where the user is a member, along with their role.
```json
// Response (200 OK)
[
  {
    "id": "c1a01c80-60b5-4b35-8664-884bf6a2de62",
    "name": "Acme Corp Production",
    "slug": "acme-corp",
    "plan": "pro",
    "role": "owner"
  }
]
```

### 3.3 Role-Based Access Control (RBAC) Matrix
Frontend components should hide/disable action buttons based on the user's role in the active organization:

| Role | Hierarchy Weight | Can View Dashboard | Can Add/Edit Dependencies | Can Acknowledge/Resolve Incidents | Can Manage Members & Billing | Can Delete Org |
|---|---|---|---|---|---|---|
| **Owner** | `40` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Admin** | `30` | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Member** | `20` | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Viewer** | `10` | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## 4. Dashboard Integration (Main Landing Screen)

The dashboard module provides pre-aggregated analytics endpoints designed for single-query widget rendering.

### 4.1 Executive Summary Cards (`GET /v1/orgs/{org_id}/dashboard/summary`)
Use this endpoint for top-level KPI cards.

```json
// Response (200 OK)
{
  "total_dependencies": 12,
  "active_incidents": 1,
  "uptime_24h": 99.94,
  "uptime_7d": 99.88,
  "avg_latency_ms": 142.5,
  "checks_24h": 8640
}
```

### 4.2 Multi-Region Latency Chart (`GET /v1/orgs/{org_id}/dashboard/latency?hours=24`)
Returns time-series latency data suitable for charting libraries (**Recharts**, **Chart.js**, **Tremor**, or **ECharts**).

```json
// Response (200 OK)
[
  {
    "timestamp": "2026-08-11T16:00:00Z",
    "region": "us-east-1",
    "latency_ms": 110.2
  },
  {
    "timestamp": "2026-08-11T16:00:00Z",
    "region": "eu-west-1",
    "latency_ms": 145.8
  }
]
```

### 4.3 SLA Degradation Widget (`GET /v1/orgs/{org_id}/dashboard/sla-degradation`)
```json
// Response (200 OK)
{
  "total_degradation_pct": 0.12,
  "affected_services": 1,
  "period": "30d"
}
```

---

## 5. Dependencies & Live Check Monitoring Grid

### 5.1 List Monitored Dependencies (`GET /v1/orgs/{org_id}/dependencies`)
```json
// Response (200 OK)
[
  {
    "id": "e0cf5c49-d191-4a41-b01c-343285cf4432",
    "name": "Stripe Billing API",
    "target_url": "https://api.stripe.com/v1/charges",
    "check_interval_seconds": 10,
    "expected_status_code": 200,
    "is_active": true,
    "headers": {
      "Authorization": "Bearer sk_test_..."
    },
    "created_at": "2026-08-11T10:00:00Z"
  }
]
```

### 5.2 Create Dependency (`POST /v1/orgs/{org_id}/dependencies`)
```json
// Request Body
{
  "name": "OpenAI Chat Completions",
  "target_url": "https://api.openai.com/v1/models",
  "check_interval_seconds": 10,
  "expected_status_code": 200,
  "headers": {
    "Authorization": "Bearer sk-proj-..."
  }
}
```

### 5.3 Recent Check Execution Live Feed (`GET /v1/orgs/{org_id}/checks/recent?limit=50`)
Poll this endpoint (or use SWR / TanStack Query with a 10s refresh interval) to render live status badges and regional consensus indicators.

```json
// Response (200 OK)
[
  {
    "id": "7f8b9a23-45c1-4d3e-9021-123456789abc",
    "dependency_id": "e0cf5c49-d191-4a41-b01c-343285cf4432",
    "region": "us-east-1",
    "status_code": 200,
    "response_time_ms": 115.4,
    "is_up": true,
    "quorum_confirmed": true,
    "executed_at": "2026-08-11T17:15:10Z"
  }
]
```

---

## 6. Incidents & SLA Evidence Pipeline UI

### 6.1 List Incidents & Correlated Vendor Outages (`GET /v1/orgs/{org_id}/incidents?status_filter=open`)
Each incident object includes **Temporal Correlation** data showing if another vendor service failed in the same $\pm5\text{ minute}$ window.

```json
// Response (200 OK)
[
  {
    "id": "90123456-789a-bcde-f012-3456789abcde",
    "title": "Outage detected on Stripe Billing API",
    "status": "open",
    "severity": "critical",
    "started_at": "2026-08-11T16:50:00Z",
    "resolved_at": null,
    "correlations": [
      {
        "correlated_dependency_id": "a1b2c3d4-e5f6-7890-1234-56789abcdef0",
        "correlation_type": "temporal_coincidence",
        "confidence_score": 0.85
      }
    ]
  }
]
```

### 6.2 Resolve an Incident (`POST /v1/orgs/{org_id}/incidents/{id}/resolve`)
```json
// Request Body
{
  "summary": "Vendor confirmed network recovery; quorum checks passing across us-east-1 and eu-west-1."
}

// Response (200 OK)
{
  "id": "90123456-789a-bcde-f012-3456789abcde",
  "status": "resolved",
  "resolved_at": "2026-08-11T17:10:00Z"
}
```

### 6.3 Generate SLA Evidence Report (`POST /v1/orgs/{org_id}/evidence/generate`)
Triggers asynchronous HTML-to-PDF rendering via Playwright with cryptographic SHA-256 integrity checksum calculation.

```json
// Request Body
{
  "incident_id": "90123456-789a-bcde-f012-3456789abcde",
  "title": "SLA Degradation Report — Stripe Billing Outage",
  "include_charts": true
}

// Response (201 Created)
{
  "id": "b1c2d3e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e",
  "title": "SLA Degradation Report — Stripe Billing Outage",
  "status": "completed",
  "file_url": "http://localhost:9000/evidence-reports/b1c2d3e4...pdf",
  "sha256_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "created_at": "2026-08-11T17:15:00Z"
}
```

---

## 7. Global Public Vendor Status Board (`GET /v1/public/vendors`)

This public endpoint requires no authentication and returns real-time uptime status for 5 major third-party cloud services tracked by Reliastra:
- **Stripe** (`stripe`)
- **Auth0** (`auth0`)
- **Cloudflare** (`cloudflare`)
- **OpenAI** (`openai`)
- **Twilio** (`twilio`)

```json
// Response (200 OK)
[
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "vendor_name": "Stripe API",
    "slug": "stripe",
    "current_status": "operational",
    "uptime_90d": 99.99,
    "last_checked_at": "2026-08-11T17:15:00Z"
  }
]
```

---

## 8. Notification Alert Channels (`GET | POST /v1/orgs/{org_id}/notifications`)

Supports four extensible Strategy Pattern channels: `email`, `slack`, `pagerduty`, and `webhook`.

```json
// POST /v1/orgs/{org_id}/notifications - Create Channel Request
{
  "channel_type": "slack",
  "config": {
    "webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX"
  },
  "is_active": true
}
```

---

## 9. API Keys (`GET | POST /v1/orgs/{org_id}/api-keys`)

Creates SHA-256 hashed API keys for programmatic access. **Important for Frontend**: The raw API key string is returned **only once upon creation**. Display it in a secure modal with a copy button.

```json
// POST /v1/orgs/{org_id}/api-keys - Request Body
{
  "name": "GitHub Actions CI Production Key"
}

// Response (201 Created)
{
  "id": "f5e4d3c2-b1a0-9876-5432-10abcdef9876",
  "name": "GitHub Actions CI Production Key",
  "key_prefix": "rel_c8a9...",
  "raw_key": "rel_c8a9f0e1d2c3b4a59687786950413223", // DISPLAY ONCE!
  "created_at": "2026-08-11T17:15:00Z"
}
```

---

## 10. Billing & Plan Usage (`GET /v1/orgs/{org_id}/billing/plan`)

Use this endpoint to render usage meters in the Organization Settings UI.

```json
// Response (200 OK)
{
  "plan_name": "pro",
  "max_dependencies": 25,
  "current_dependencies": 12,
  "max_team_members": 10,
  "current_team_members": 3,
  "can_add_dependency": true
}
```

---

## 11. TypeScript Integration Reference & Axios Client Wrapper

Copy and paste this TypeScript API client wrapper into your frontend project (`src/lib/api.ts`):

```typescript
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000,
});

// Request Interceptor: Attach access token & idempotency keys
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("reliastra_access_token");
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Attach idempotency key for mutations
  if (["post", "put", "delete", "patch"].includes(config.method || "")) {
    config.headers["Idempotency-Key"] = crypto.randomUUID();
  }
  return config;
});

// Response Interceptor: Silent token rotation on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem("reliastra_refresh_token");

      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem("reliastra_access_token", data.access_token);
          if (data.refresh_token) {
            localStorage.setItem("reliastra_refresh_token", data.refresh_token);
          }
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
          }
          return apiClient(originalRequest);
        } catch (refreshError) {
          localStorage.removeItem("reliastra_access_token");
          localStorage.removeItem("reliastra_refresh_token");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);
```

### 11.2 Typed API Functions Example (`src/services/dashboardService.ts`)

```typescript
import { apiClient } from "@/lib/api";

export interface DashboardSummary {
  total_dependencies: number;
  active_incidents: number;
  uptime_24h: number;
  uptime_7d: number;
  avg_latency_ms: number;
  checks_24h: number;
}

export interface LatencyPoint {
  timestamp: string;
  region: string;
  latency_ms: number;
}

export const getDashboardSummary = async (orgId: string): Promise<DashboardSummary> => {
  const { data } = await apiClient.get<DashboardSummary>(`/orgs/${orgId}/dashboard/summary`);
  return data;
};

export const getDashboardLatency = async (orgId: string, hours = 24): Promise<LatencyPoint[]> => {
  const { data } = await apiClient.get<LatencyPoint[]>(`/orgs/${orgId}/dashboard/latency?hours=${hours}`);
  return data;
};
```
