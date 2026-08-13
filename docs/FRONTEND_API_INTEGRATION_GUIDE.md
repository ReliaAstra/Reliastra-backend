# Reliastra Frontend & Dashboard Integration Guide

This guide provides frontend and dashboard developers with complete integration specifications, TypeScript type definitions, exact request/response payloads, and UI patterns for integrating with the **Reliastra External Dependency Intelligence Backend**.

---

## 1. Core Integration Concepts

- **Base URL**: All REST endpoints are prefixed with `/v1`.
  - Local development: `http://localhost:8000/v1`
  - OpenAPI Spec: `http://localhost:8000/openapi.json` (exported locally to `docs/openapi.json`)
  - Swagger UI: `http://localhost:8000/docs`
- **CORS**: The backend is configured via `CORS_ORIGINS` env var. Default: `http://localhost:3000`, `http://localhost:8000`. Set this to your production frontend domain when deploying.
- **Idempotency Header**: For mutation requests (`POST`, `PUT`, `DELETE`), include a unique UUID in the `Idempotency-Key` HTTP header. The backend caches the response in Redis for 24 hours to prevent duplicate submissions on network retries.
- **Error Responses**: Standardized JSON error envelope across all endpoints:
  ```json
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Input validation failed",
      "details": {
        "errors": [{"loc": ["field"], "msg": "error description"}]
      }
    }
  }
  ```

---

## 2. Authentication & Session Lifecycle

The platform supports **Triple Authentication**:
1. **Email/Password** — traditional registration and login with bcrypt-hashed passwords.
2. **Google OAuth 2.0** — one-click sign-up/sign-in via Google account.
3. **GitHub OAuth 2.0** — one-click sign-up/sign-in via GitHub account.
4. **API Keys** (`rel_...`) for automated CI/CD and script integrations.

All human-facing auth methods (email, Google, GitHub) return the same JWT token pair (`access_token` + `refresh_token`). OAuth flows also return additional user metadata (`is_new_user`, `user_id`, `email`, `full_name`).

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
Revokes the refresh token in Redis and PostgreSQL.
```json
// Request Body
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn..."
}
// Response (204 No Content — empty body)
```

### 2.3 Google OAuth 2.0 Flow

#### **GET /v1/auth/google/url**
Returns the Google OAuth consent screen URL and a CSRF `state` token.
```json
// Response (200 OK)
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&scope=openid+email+profile&...",
  "state": "random_csrf_state_token_32_bytes"
}
```

**Frontend implementation:**
1. Call this endpoint to get the URL and state.
2. Store the `state` in session storage (for CSRF validation).
3. Redirect `window.location.href` to the `authorization_url`.
4. Google redirects back to your `GOOGLE_REDIRECT_URI` with `?code=...&state=...`.
5. Verify the `state` matches, then call `/v1/auth/google` with the code.

#### **POST /v1/auth/google**
Exchange the Google authorization code for Reliastra JWT tokens.
```json
// Request Body
{
  "code": "4/0AX4XfWg..."
}

// Response (200 OK)
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900,
  "is_new_user": true,
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@gmail.com",
  "full_name": "John Doe"
}
```

**Key response fields:**
- `is_new_user`: `true` if this was a first-time Google sign-up (new account created). `false` if the user already existed (sign-in or account link).
- Use `is_new_user` to show a "Welcome! Complete your profile" onboarding flow vs. a direct redirect to the dashboard.
- Store tokens in `localStorage` exactly like email auth (same token format).

### 2.4 GitHub OAuth 2.0 Flow

#### **GET /v1/auth/github/url**
Returns the GitHub OAuth authorization URL and a CSRF `state` token.
```json
// Response (200 OK)
{
  "authorization_url": "https://github.com/login/oauth/authorize?client_id=...&scope=read:user+user:email&...",
  "state": "random_csrf_state_token_32_bytes"
}
```

**Frontend implementation:**
1. Call this endpoint to get the URL and state.
2. Store the `state` in session storage (for CSRF validation).
3. Redirect `window.location.href` to the `authorization_url`.
4. GitHub redirects back to your `GITHUB_REDIRECT_URI` with `?code=...&state=...`.
5. Verify the `state` matches, then call `/v1/auth/github` with the code.

#### **POST /v1/auth/github**
Exchange the GitHub authorization code for Reliastra JWT tokens.
```json
// Request Body
{
  "code": "a28f3eb5e6b1e7d2c9a0..."
}

// Response (200 OK)
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900,
  "is_new_user": true,
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@users.noreply.github.com",
  "full_name": "octocat"
}
```

**GitHub-specific notes:**
- GitHub users can keep their email private. The backend uses a multi-tier resolution: public profile email > primary verified email > any verified email > `login@users.noreply.github.com`.
- If the response email is a `noreply.github.com` address, prompt the user to update their email in account settings.
- The `full_name` field uses the GitHub `name` if available, otherwise falls back to the GitHub `login` (username).

### 2.5 Email Verification Flow

New users are created with `is_email_verified=false`. To verify, the frontend triggers the two-step flow below.

#### **POST /v1/auth/send-verification**
Sends a verification email with a one-time link to the user's inbox. **Rate limited.** All previous unexpired tokens for this user are automatically revoked.
```json
// Request Body
{
  "email": "admin@reliastra.dev"
}

// Response (200 OK)
{
  "message": "Verification email sent. Check your inbox.",
  "email": "admin@reliastra.dev"
}

// Error (404) — if no account exists with this email
// Error (400, EMAIL_ALREADY_VERIFIED) — if email is already verified
```

#### **POST /v1/auth/verify-email**
Consumes the token from the verification link and marks the user's email as verified.
```json
// Request Body
{
  "token": "token_from_email_link"
}

// Response (200 OK)
{
  "message": "Email verified successfully.",
  "is_email_verified": true
}

// Error (422, INVALID_TOKEN) — token not found
// Error (422, TOKEN_ALREADY_USED) — token was already consumed
// Error (422, TOKEN_EXPIRED) — token expired (> 60 minutes)
```

**Frontend implementation:**
1. After registration, show a "Verify your email" banner with a "Resend verification" button.
2. On click, call `POST /v1/auth/send-verification` with the user's email.
3. The email contains a link to `{FRONTEND_BASE_URL}/verify-email?token={token}`.
4. On the verification page, extract the token from the URL query parameter and call `POST /v1/auth/verify-email`.
5. On success, update the user's local state to reflect `is_email_verified: true`.

### 2.6 Password Reset Flow

The password reset flow uses anti-enumeration — the same generic message is returned whether or not the email exists in the database, preventing attackers from discovering which emails are registered.

#### **POST /v1/auth/forgot-password**
Sends a password reset email if an account exists with the given email. **Rate limited.** All previous unexpired tokens for this user are automatically revoked.
```json
// Request Body
{
  "email": "admin@reliastra.dev"
}

// Response (200 OK) — ALWAYS returns this, even if email doesn't exist
{
  "message": "If an account with this email exists, a password reset link has been sent."
}
```

#### **POST /v1/auth/reset-password**
Consumes the token from the reset link and sets the new password.
```json
// Request Body
{
  "token": "token_from_email_link",
  "new_password": "NewSecurePassword123!"
}

// Response (200 OK)
{
  "message": "Password has been reset successfully. You can now log in with your new password."
}

// Validation Error (422) — password must be at least 8 characters
// Error (422, INVALID_TOKEN) — token not found
// Error (422, TOKEN_ALREADY_USED) — token was already consumed
// Error (422, TOKEN_EXPIRED) — token expired (> 15 minutes)
```

**Frontend implementation:**
1. On the "Forgot Password" page, collect the email and call `POST /v1/auth/forgot-password`.
2. Always show the success message ("Check your inbox") regardless of the response — do not reveal whether the email exists.
3. The email contains a link to `{FRONTEND_BASE_URL}/reset-password?token={token}`.
4. On the reset password page, extract the token from the URL, collect the new password (with confirmation), and call `POST /v1/auth/reset-password`.
5. On success, redirect to the login page with a success flash message.

### 2.7 Account Linking Across Providers

All three auth methods (email, Google, GitHub) are unified by **email address**. If a user registers with `admin@reliastra.dev` via email and later signs in with Google using the same email, the Google identity is linked to the existing account — no duplicate is created. The same applies for GitHub.

**Frontend UX recommendations:**
- On the login page, show "Continue with Google" and "Continue with GitHub" buttons alongside the email/password form.
- After OAuth redirect, check `is_new_user` to route to either onboarding or dashboard.
- In account settings, display the user's linked providers (show badges for Google, GitHub, Email).

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
**IMPLEMENTED IN PHASE 8.** Returns organization-scoped observation time-series data suitable for charting libraries (**Recharts**, **Chart.js**, **Tremor**, or **ECharts**).

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

### 4.3 SLA Degradation Widget (`GET /v1/orgs/{org_id}/dashboard/sla-degradation?period_days=30`)
**IMPLEMENTED IN PHASE 8.** Aggregates degradation from immutable observations.

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

### 6.2 Resolve an Incident (`PATCH /v1/orgs/{org_id}/incidents/{inc_id}`)
```json
// Request Body
{
  "status": "resolved"
}

// Response (200 OK)
{
  "id": "90123456-789a-bcde-f012-3456789abcde",
  "status": "resolved",
  "resolved_at": "2026-08-11T17:10:00Z"
}
```

### 6.3 SLA Evidence Generation (Automatic)
Resolving an incident automatically runs deterministic 5-signal attribution and queues immutable PDF and JSON evidence generation. Use `GET /v1/orgs/{org_id}/incidents/{inc_id}/evidence` to retrieve the generated report.

### 6.4 Public Evidence Verification (`GET /v1/verify/{verification_id}`)
This public endpoint requires no authentication and provides cryptographic verification of any evidence snapshot:
```json
// Response (200 OK)
{
  "found": true,
  "incident_id": "uuid",
  "dependency_id": "uuid",
  "org_id": "uuid",
  "time_window": {
    "start": "2026-08-11T16:00:00Z",
    "end": "2026-08-11T17:00:00Z"
  },
  "data_hash": "sha256:...",
  "report_checksum": "sha256:...",
  "methodology_version": "1.0",
  "created_at": "2026-08-11T17:05:00Z"
}
```

---

## 7. Global Public Vendor Status Board

### 7.1 List Vendors (`GET /v1/public/vendors`)
Public endpoint (no auth required). Returns tracked vendor status.

### 7.2 Vendor Detail (`GET /v1/public/vendors/{vendor_name}`)
Returns detailed status for a specific vendor.

### 7.3 Vendor History (`GET /v1/public/vendors/{vendor_name}/history`)
Returns historical uptime data.

### 7.4 Vendor Incidents (`GET /v1/public/vendors/{vendor_name}/incidents`)
Returns incidents associated with a vendor.

### 7.5 Vendor Metrics (`GET /v1/public/vendors/{vendor_name}/metrics`)
Returns uptime and latency metrics for charting.

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

## 10. Paystack Billing & Plan Usage

Use `GET /v1/orgs/{org_id}/billing/plan` to render plan limits and subscription state.

```json
// Response (200 OK)
{
  "org_id": "11111111-1111-1111-1111-111111111111",
  "plan": "standard",
  "max_dependencies": 25,
  "min_check_interval_seconds": 60,
  "subscription_status": "active",
  "current_period_end": "2026-09-12T00:00:00Z"
}
```

Initialize Paystack checkout with `POST /v1/orgs/{org_id}/billing/initialize` and body `{"plan":"standard","email":"owner@example.com"}`. After checkout, verify the Paystack reference with `POST /v1/billing/verify?reference={reference}`. Payment state is finalized from signed Paystack webhooks; never update an organization plan from client-side state alone.

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

### 11.3 OAuth Typed API Functions (`src/services/authService.ts`)

```typescript
import { apiClient } from "@/lib/api";

// ── Shared OAuth Types ──────────────────────────────────────────────

export interface OAuthUrlResponse {
  authorization_url: string;
  state: string;
}

export interface OAuthCallbackResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
  user_id: string;
  email: string;
  full_name: string;
}

// ── Google OAuth ──────────────────────────────────────────────────────

export const getGoogleAuthUrl = async (): Promise<OAuthUrlResponse> => {
  const { data } = await apiClient.get<OAuthUrlResponse>("/auth/google/url");
  return data;
};

export const exchangeGoogleCode = async (code: string): Promise<OAuthCallbackResponse> => {
  const { data } = await apiClient.post<OAuthCallbackResponse>("/auth/google", { code });
  return data;
};

/** Initiates Google OAuth flow: stores state, redirects to Google consent screen. */
export const initiateGoogleLogin = async () => {
  const { authorization_url, state } = await getGoogleAuthUrl();
  sessionStorage.setItem("google_oauth_state", state);
  window.location.href = authorization_url;
};

/** Handles Google OAuth callback: extracts code, exchanges for tokens. */
export const handleGoogleCallback = async () => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const returnedState = params.get("state");
  const savedState = sessionStorage.getItem("google_oauth_state");

  if (!code) throw new Error("No authorization code received from Google");
  if (returnedState !== savedState) throw new Error("OAuth state mismatch — possible CSRF");

  sessionStorage.removeItem("google_oauth_state");
  return await exchangeGoogleCode(code);
};

// ── GitHub OAuth ──────────────────────────────────────────────────────

export const getGitHubAuthUrl = async (): Promise<OAuthUrlResponse> => {
  const { data } = await apiClient.get<OAuthUrlResponse>("/auth/github/url");
  return data;
};

export const exchangeGitHubCode = async (code: string): Promise<OAuthCallbackResponse> => {
  const { data } = await apiClient.post<OAuthCallbackResponse>("/auth/github", { code });
  return data;
};

/** Initiates GitHub OAuth flow: stores state, redirects to GitHub consent screen. */
export const initiateGitHubLogin = async () => {
  const { authorization_url, state } = await getGitHubAuthUrl();
  sessionStorage.setItem("github_oauth_state", state);
  window.location.href = authorization_url;
};

/** Handles GitHub OAuth callback: extracts code, exchanges for tokens. */
export const handleGitHubCallback = async () => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const returnedState = params.get("state");
  const savedState = sessionStorage.getItem("github_oauth_state");

  if (!code) throw new Error("No authorization code received from GitHub");
  if (returnedState !== savedState) throw new Error("OAuth state mismatch — possible CSRF");

  sessionStorage.removeItem("github_oauth_state");
  return await exchangeGitHubCode(code);
};
```

### 11.4 OAuth Callback Page Example (`src/app/auth/callback/page.tsx`)

```typescript
"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { handleGoogleCallback, handleGitHubCallback } from "@/services/authService";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const provider = searchParams.get("provider"); // "google" or "github"

  useEffect(() => {
    const completeOAuth = async () => {
      try {
        const result = provider === "github"
          ? await handleGitHubCallback()
          : await handleGoogleCallback();

        // Store JWT tokens
        localStorage.setItem("reliastra_access_token", result.access_token);
        localStorage.setItem("reliastra_refresh_token", result.refresh_token);

        // Route based on whether this is a new user
        if (result.is_new_user) {
          router.push("/onboarding");
        } else {
          router.push("/dashboard");
        }
      } catch (error) {
        console.error("OAuth callback failed:", error);
        router.push("/login?error=oauth_failed");
      }
    };

    completeOAuth();
  }, [provider, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-gray-500">Completing sign-in...</p>
    </div>
  );
}
```

### 11.5 Email Verification & Password Reset Typed Functions (`src/services/emailAuthService.ts`)

```typescript
import { apiClient } from "@/lib/api";

// ── Email Verification ──────────────────────────────────────────────

export interface SendVerificationResponse {
  message: string;
  email: string;
}

export interface VerifyEmailResponse {
  message: string;
  is_email_verified: boolean;
}

/** Requests a new email verification link. Rate limited (ip_limiter). */
export const sendVerificationEmail = async (email: string): Promise<SendVerificationResponse> => {
  const { data } = await apiClient.post<SendVerificationResponse>("/auth/send-verification", { email });
  return data;
};

/** Verifies email using the token from the verification link. */
export const verifyEmail = async (token: string): Promise<VerifyEmailResponse> => {
  const { data } = await apiClient.post<VerifyEmailResponse>("/auth/verify-email", { token });
  return data;
};

// ── Password Reset ──────────────────────────────────────────────────

export interface ForgotPasswordResponse {
  message: string;
}

export interface ResetPasswordResponse {
  message: string;
}

/**
 * Requests a password reset email. Always returns a generic success message
 * (anti-enumeration — does not reveal whether the email exists). Rate limited.
 */
export const forgotPassword = async (email: string): Promise<ForgotPasswordResponse> => {
  const { data } = await apiClient.post<ForgotPasswordResponse>("/auth/forgot-password", { email });
  return data;
};

/** Resets the user's password using the token from the reset email link. */
export const resetPassword = async (token: string, newPassword: string): Promise<ResetPasswordResponse> => {
  const { data } = await apiClient.post<ResetPasswordResponse>("/auth/reset-password", {
    token,
    new_password: newPassword,
  });
  return data;
};
```

### 11.6 Verification & Reset Page Example (`src/app/auth/verify-email/page.tsx`)

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { verifyEmail } from "@/services/emailAuthService";

export default function VerifyEmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      setErrorMsg("No verification token found in URL.");
      return;
    }

    const doVerify = async () => {
      try {
        const result = await verifyEmail(token);
        if (result.is_email_verified) {
          setStatus("success");
          // Redirect to dashboard after a brief success message
          setTimeout(() => router.push("/dashboard"), 2000);
        }
      } catch (error: any) {
        setStatus("error");
        setErrorMsg(error?.response?.data?.error?.message || "Verification failed. The link may have expired.");
      }
    };

    doVerify();
  }, [searchParams, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      {status === "loading" && <p className="text-gray-500">Verifying your email...</p>}
      {status === "success" && (
        <div className="text-center">
          <p className="text-green-600 font-medium">Email verified successfully!</p>
          <p className="text-gray-400 text-sm mt-1">Redirecting to dashboard...</p>
        </div>
      )}
      {status === "error" && (
        <div className="text-center">
          <p className="text-red-500 font-medium">{errorMsg}</p>
          <button
            className="mt-4 text-sm text-blue-600 hover:underline"
            onClick={() => router.push("/login")}
          >
            Go to Login
          </button>
        </div>
      )}
    </div>
  );
}
```

### 11.7 Reset Password Page Example (`src/app/auth/reset-password/page.tsx`)

```typescript
"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { resetPassword } from "@/services/emailAuthService";

export default function ResetPasswordPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "form" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    // If there's no token, show the "forgot password" entry point instead
    const token = searchParams.get("token");
    if (token) {
      setStatus("form");
    } else {
      router.push("/forgot-password");
    }
  }, [searchParams, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg("Passwords do not match.");
      return;
    }

    try {
      const token = searchParams.get("token")!;
      await resetPassword(token, password);
      setStatus("success");
      setTimeout(() => router.push("/login?reset=success"), 2000);
    } catch (error: any) {
      setStatus("error");
      setErrorMsg(error?.response?.data?.error?.message || "Failed to reset password. The link may have expired.");
    }
  };

  if (status === "loading") {
    return <div className="flex items-center justify-center min-h-screen"><p className="text-gray-500">Loading...</p></div>;
  }

  if (status === "success") {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-green-600 font-medium">Password reset successfully!</p>
          <p className="text-gray-400 text-sm mt-1">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 p-6 bg-white rounded-lg shadow-md">
        <h2 className="text-xl font-semibold text-center">Set New Password</h2>

        {status === "error" && (
          <p className="text-red-500 text-sm text-center">{errorMsg}</p>
        )}

        <input
          type="password"
          placeholder="New password (min. 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full px-3 py-2 border rounded-md"
          minLength={8}
          required
        />

        <input
          type="password"
          placeholder="Confirm new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="w-full px-3 py-2 border rounded-md"
          minLength={8}
          required
        />

        <button
          type="submit"
          className="w-full py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Reset Password
        </button>
      </form>
    </div>
  );
}
```
