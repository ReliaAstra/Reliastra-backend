# Reliastra API changelog (frontend & SDK)

This is a **breaking** release. Update clients before deploying.

## Auth

`POST /v1/auth/register` now returns a single payload:

```json
{
  "user": { "id": "...", "email": "...", "full_name": "...", "is_active": true },
  "organization": { "id": "...", "name": "...", "slug": "...", "plan": "free" },
  "tokens": { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 900 }
}
```

A default organization is created automatically. Do **not** call `POST /v1/orgs` as a required signup step.

Login / refresh still return the token object only.

## Tenant context

`{org_id}` is no longer a path parameter.

Send one of:

- `X-Organization-ID: <uuid>`
- `Reliastra-Organization: <uuid>`

Examples:

| Old | New |
| --- | --- |
| `GET /v1/orgs/{org_id}/dependencies` | `GET /v1/dependencies` |
| `POST /v1/orgs/{org_id}/incidents` | `POST /v1/incidents` |
| `GET /v1/orgs/{org_id}` | `GET /v1/orgs/current` |
| `GET /v1/orgs/{org_id}/members` | `GET /v1/orgs/members` |

`GET /v1/orgs` still lists the caller's organizations (no header required).

## Pagination

All list endpoints use cursor pagination:

```
GET /v1/dependencies?limit=50&cursor=<next_cursor>
```

```json
{
  "data": [ ... ],
  "pagination": { "next_cursor": "abc", "has_more": true, "limit": 50 }
}
```

Legacy `items` / `next_cursor` / `has_more` / `total` fields are still present for one release.

## Public API

The `/v1/public/` prefix is gone. Same resources live at the canonical path.

| Old | New |
| --- | --- |
| `/v1/public/vendors` | `/v1/vendors` |
| `/v1/public/vendors/{name}/incidents` | `/v1/vendors/{name}/incidents?public=true` |
| `/v1/public/referral/{code}` | `/v1/referral/{code}` |
| `/v1/public/partners` | `/v1/partners` (directory) |
| `/v1/public/evidence/{token}/download` | `/v1/evidence/{token}/download` |
| `/v1/public/pricing` | `/v1/pricing` |
| `/v1/public/feed` | `/v1/feed` |
| `/v1/public/status` | `/v1/status` |

Optional `?public=true` documents unauthenticated access; public routes do not require auth.

## Errors

Every 4xx/5xx body is:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid field: email",
    "details": [{ "field": "email", "issue": "must be a valid email address" }],
    "request_id": "req_abc123"
  }
}
```

`X-Request-ID` is echoed on every response.

## Evidence report tokens

`report_token` TTL is **7 days**. Gate responses include `report_token` and `expires_at`.

## Founding customer program removed

The private founding customer program is retired. The following endpoints are
**gone** (404):

| Removed |
| --- |
| `GET /v1/billing/founding-spots` |
| `POST /v1/billing/founding-spot/claim` |
| `GET /v1/admin/business/founding-customers` |

`GET /v1/billing/plan` no longer returns `is_founding_customer`,
`founding_discount_pct` or `discounted_price_usd` — every organization is
charged the published plan price (`price_usd`).

## Admin control plane (2026-08)

The platform admin API is reorganized into an operational control plane.
Legacy module-oriented routes remain available and are marked **deprecated**
in OpenAPI. Prefer the canonical surface below.

Full mapping: [`docs/ADMIN_CONTROL_PLANE.md`](./ADMIN_CONTROL_PLANE.md).

### Bootstrap

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/v1/admin/overview` | Primary admin home payload |
| `GET` | `/v1/admin/attention` | Prioritized action-required alerts |
| `GET` | `/v1/admin/search?q=` | Global admin search |

### Customers (replaces `/v1/admin/users`)

| Method | Path |
| --- | --- |
| `GET` | `/v1/admin/customers` |
| `GET` | `/v1/admin/customers/recent` |
| `GET` | `/v1/admin/customers/churn-risk` |
| `GET` | `/v1/admin/customers/{customer_id}` |
| `PATCH` | `/v1/admin/customers/{customer_id}` |
| `POST` | `/v1/admin/customers/{customer_id}/impersonate` |
| `POST` | `/v1/admin/customers/{customer_id}/plan` |
| `POST` | `/v1/admin/customers/{customer_id}/email` |
| `POST` | `/v1/admin/customers/{customer_id}/deactivate` |
| `GET` | `/v1/admin/customers/{customer_id}/activity` |

Impersonation now requires `{ "reason": "..." }` and returns a short-lived
access token only (no refresh).

### Revenue / Growth / Product

```
GET /v1/admin/revenue/summary|timeseries|attention
GET /v1/admin/growth/overview|funnel|retention|referrals
GET /v1/admin/product/overview|features|vendors|engagement|activation
```

### Support / Communications / Operations

```
GET  /v1/admin/support/overview
GET  /v1/admin/support/tickets/{id}   # full workspace (customer + billing context)
GET  /v1/admin/communications/overview
GET  /v1/admin/operations/overview
GET  /v1/admin/operations/errors      # was /error-logs
```

Partners (`/v1/admin/partners/*`) and vendor-submission tenant-admin routes
are unchanged.
