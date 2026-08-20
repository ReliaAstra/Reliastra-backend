# Admin Control Plane

Production backend simplification of the Reliastra **admin API / operating console**.

Mental model:

```text
Investment portfolio dashboard + mission control + operating console
```

```text
OPEN ADMIN
    ↓
GET /v1/admin/overview
GET /v1/admin/attention
    ↓
SEE WHAT MATTERS
    ↓
CLICK CUSTOMER / TICKET / REVENUE / PARTNER
    ↓
GET COMPLETE CONTEXT
    ↓
TAKE ONE CLEAR ACTION (audited)
```

---

## Endpoint mapping

| Previous | Decision | Canonical |
|----------|----------|-----------|
| `GET /v1/admin/business/summary` | **DEPRECATE** | `GET /v1/admin/overview` + `GET /v1/admin/revenue/summary` |
| `GET /v1/admin/business/mrr-timeseries` | **DEPRECATE** | `GET /v1/admin/revenue/timeseries` |
| `GET /v1/admin/business/recent-signups` | **DEPRECATE** | `GET /v1/admin/customers/recent` |
| `GET /v1/admin/business/churn-signals` | **DEPRECATE** | `GET /v1/admin/customers/churn-risk` |
| `GET /v1/admin/business/founding-customers` | **REMOVED** (founding program retired) | — |
| `GET /v1/admin/analytics/growth-funnel` | **DEPRECATE** | `GET /v1/admin/growth/funnel` |
| `GET /v1/admin/analytics/retention` | **DEPRECATE** | `GET /v1/admin/growth/retention` |
| `GET /v1/admin/analytics/feature-adoption` | **DEPRECATE** | `GET /v1/admin/product/features` |
| `GET /v1/admin/analytics/vendor-coverage` | **DEPRECATE** | `GET /v1/admin/product/vendors` |
| `GET /v1/admin/analytics/time-to-value` | **DEPRECATE** | `GET /v1/admin/product/activation` |
| `GET /v1/admin/analytics/engagement` | **DEPRECATE** | `GET /v1/admin/product/engagement` |
| `GET /v1/admin/growth/funnel` (owner-auth PLG) | **REPLACE** | Canonical funnel under system admin; PLG details in `plg` field. Legacy PLG shape at `/v1/admin/growth/plg-funnel` |
| `GET /v1/admin/growth/top-vendors` | **DEPRECATE** | `GET /v1/admin/product/vendors` |
| `GET /v1/admin/growth/referral-stats` | **DEPRECATE** | `GET /v1/admin/growth/referrals` (PLG) / `GET /v1/admin/partners/stats` (partner program) |
| `GET/PATCH /v1/admin/users*` | **DEPRECATE** | `/v1/admin/customers*` |
| `POST /v1/admin/users/override-plan` | **DEPRECATE** | `POST /v1/admin/customers/{id}/plan` |
| `POST /v1/admin/users/send-email` | **DEPRECATE** | `POST /v1/admin/customers/{id}/email` |
| `POST /v1/admin/users/{id}/impersonate` | **DEPRECATE** | `POST /v1/admin/customers/{id}/impersonate` (requires `reason`) |
| `GET /v1/admin/operations/health` | **DEPRECATE** | `GET /v1/admin/operations/overview` |
| `GET /v1/admin/operations/check-engines` | **DEPRECATE** | `GET /v1/admin/operations/overview` |
| `GET /v1/admin/operations/error-logs` | **DEPRECATE** | `GET /v1/admin/operations/errors` |
| `GET /v1/admin/support/tickets/stats` | **DEPRECATE** | `GET /v1/admin/support/overview` |
| Support ticket CRUD / reply / bulk | **KEEP** | Same paths; ticket detail is now a full workspace |
| Communications campaigns / notifications / announcements | **KEEP** | Plus `GET /v1/admin/communications/overview` |
| Partners admin surface | **KEEP** | Unchanged lean surface |
| Vendor submissions (`/v1/vendors/submissions*`) | **KEEP** | Tenant-admin, not platform control plane |

Legacy routes remain registered and are marked `deprecated=true` in OpenAPI.

---

## Canonical surface

### Bootstrap (admin home ≈ 3–5 requests)

```text
GET /v1/admin/overview
GET /v1/admin/attention
GET /v1/admin/revenue/timeseries?period=30d&granularity=day
GET /v1/admin/customers/recent
GET /v1/admin/search?q=...
```

### Customers

```text
GET    /v1/admin/customers
GET    /v1/admin/customers/recent
GET    /v1/admin/customers/churn-risk
GET    /v1/admin/customers/{customer_id}
PATCH  /v1/admin/customers/{customer_id}          # safe profile fields only
POST   /v1/admin/customers/{customer_id}/impersonate
POST   /v1/admin/customers/{customer_id}/plan
POST   /v1/admin/customers/{customer_id}/email
POST   /v1/admin/customers/{customer_id}/deactivate
GET    /v1/admin/customers/{customer_id}/activity
```

### Revenue

```text
GET /v1/admin/revenue/summary
GET /v1/admin/revenue/timeseries
GET /v1/admin/revenue/attention
```

### Growth

```text
GET /v1/admin/growth/overview
GET /v1/admin/growth/funnel
GET /v1/admin/growth/retention
GET /v1/admin/growth/referrals
```

### Product

```text
GET /v1/admin/product/overview
GET /v1/admin/product/features
GET /v1/admin/product/vendors
GET /v1/admin/product/engagement
GET /v1/admin/product/activation
```

### Support

```text
GET   /v1/admin/support/overview
GET   /v1/admin/support/tickets
GET   /v1/admin/support/tickets/{ticket_id}   # full workspace
POST  /v1/admin/support/tickets
PATCH /v1/admin/support/tickets/{ticket_id}
POST  /v1/admin/support/tickets/{ticket_id}/reply
POST  /v1/admin/support/tickets/bulk-update
```

### Communications

```text
GET   /v1/admin/communications/overview
POST  /v1/admin/communications/campaigns
GET   /v1/admin/communications/campaigns
GET   /v1/admin/communications/campaigns/{id}
PATCH /v1/admin/communications/campaigns/{id}
POST  /v1/admin/communications/campaigns/{id}/send
POST  /v1/admin/communications/notifications
GET   /v1/admin/communications/notifications
POST  /v1/admin/communications/announcements
GET   /v1/admin/communications/announcements
GET   /v1/admin/communications/announcements/{id}
PATCH /v1/admin/communications/announcements/{id}
```

### Operations

```text
GET /v1/admin/operations/overview
GET /v1/admin/operations/errors
GET /v1/admin/operations/metrics
```

### Audit

```text
GET /v1/admin/audit-log
```

### Partners (unchanged, lean)

```text
GET   /v1/admin/partners
GET   /v1/admin/partners/stats
GET   /v1/admin/partners/{partner_id}
PATCH /v1/admin/partners/{partner_id}
GET   /v1/admin/partners/commissions
POST  /v1/admin/partners/commissions/{id}/reverse
GET   /v1/admin/partners/payouts
POST  /v1/admin/partners/payouts
POST  /v1/admin/partners/payouts/{id}/process
```

---

## Security

- All `/v1/admin/*` control-plane routes use `require_system_admin`.
- Tenant org-admin routes (`require_admin` / `require_owner`) stay on domain paths.
- Impersonation requires an explicit `reason`, issues a short-lived access token only
  (no refresh), stamps `impersonator_id` + `type=impersonation`, and writes an audit row.
- Sensitive mutations (plan override, deactivate, campaign send, partner payouts, etc.)
  continue to write to `admin_audit_logs`.

---

## Implementation files

| File | Role |
|------|------|
| `app/modules/admin/control_plane_schemas.py` | Response/request models for aggregates |
| `app/modules/admin/control_plane_service.py` | Aggregation service composing existing repos |
| `app/modules/admin/router.py` | Canonical + deprecated route registration |
| `app/modules/growth/router.py` | Legacy growth aliases (no path conflict with canonical funnel) |
| `app/modules/partners/admin_router.py` | Unchanged partner admin surface |

---

## Frontend migration guidance

1. Point admin home at `GET /overview` + `GET /attention` (+ optional timeseries/recent).
2. Replace user screens with customers endpoints.
3. Replace analytics/business calls with growth/product/revenue namespaces.
4. Prefer ticket workspace detail — stop fan-out to customer/org/billing separately.
5. After frontend ships, remove deprecated routes in a follow-up release.
