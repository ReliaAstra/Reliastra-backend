# Partner Network & Distribution

Backend infrastructure for the RELIASTRA partner program: partner accounts,
referral attribution, an immutable commission ledger, payouts, lead
introductions, deployment claims, fraud review and country analytics.

This document covers the parts a reader cannot get from the OpenAPI spec —
the model, the invariants and the reasoning. Every endpoint is documented in
`docs/openapi.json` (57 partner/geo paths) and served at `/docs`.

---

## 1. What a partner earns, and when

Five earning methods, each a fixed rate applied to **revenue actually
collected** from the customer:

| Method      | Rate | Duration                    | Notes |
|-------------|------|-----------------------------|-------|
| `refer`     | 20%  | Recurring while active      | Someone signs up through their link and pays. |
| `deploy`    | 30%  | Recurring while active      | They implemented Reliastra for the customer. Requires a reviewed claim. |
| `create`    | 25%  | Recurring while active      | They built something on the platform. Requires a reviewed claim. |
| `introduce` | 15%  | Year 1 only, one-time basis | Warm introduction that converts. |
| `resell`    | 0%   | —                           | Compensated by wholesale margin, not platform commission. |

Rates live in configuration (`PARTNER_RATE_*_BPS`), are expressed in basis
points, and are served to clients from `GET /v1/public/partner-program` so
nothing hardcodes the economics.

**Three rules bound all of it:**

1. **Actual revenue only.** The base is the amount the payment provider
   reports as collected. A discounted or partially-refunded payment earns on
   what was really received, never on a plan's list price.
2. **50% ceiling.** The combined rate on a single payment can never exceed
   `PARTNER_MAX_TOTAL_COMMISSION_BPS`, no matter how many partners have a
   claim on that customer. When two partners qualify, the earlier
   relationship is satisfied first and the later one is clipped.
3. **Integer minor units.** Every amount is a `BIGINT` of minor units with a
   currency code. `to_minor_units()` raises on a `float` argument. Rate
   application uses `Decimal` with `ROUND_HALF_UP`, multiplying before
   dividing so no cent is lost.

Clicks are never payable. Signups are never payable on their own. Money is
created only by a verified, collected payment.

---

## 2. Links and attribution

The canonical link is

```
https://reliastra.com/r/{partner_code}            # from RELIASTRA_PUBLIC_URL
https://reliastra.com/r/{partner_code}?campaign={campaign_code}
```

Every URL in the system is produced by `ReferralLinkService`
(`app/modules/partners/links.py`) from configuration, so staging and preview
environments emit correct links without a code change, and a link in an
email is byte-identical to one in a test.

This is **separate from** the existing PLG referral programme
(`{FRONTEND_BASE_URL}/ref/{code}`, `referral_codes` / `referrals`), which is
untouched. The two answer different questions — peer rewards versus
commissionable partner ownership — and a user can arrive through both.

### The flow

1. `GET /v1/public/referral/{partner_code}` resolves the link, writes a
   `partner_click_events` row and returns an anonymous `visitor_id`.
2. The client stores that id (first-party) and replays it at signup as
   `partner_visitor_id` on `POST /v1/auth/register`.
3. Registration binds the attribution to the new user and organisation.
4. The first collected payment promotes that attribution into a
   `partner_customer_relationships` row — the durable, revenue-bearing link
   the commission engine reads.

**Last eligible touch wins**, inside a configurable 90-day window. Earlier
touches are marked `superseded` rather than deleted: rows carry
`model`, `position` and `weight_bps`, so moving to a linear or
position-based model later is a weight recalculation, not a migration.

Attribution can never fail a registration — any error is logged and
swallowed. Self-referral is detected and voided at bind time.

UTM parameters are captured on the click and the attribution touch for
analytics. They **never** influence who owns a conversion; a crafted
`utm_source` cannot take a customer from the partner whose link was used.

---

## 3. The commission ledger

`partner_commissions` is append-only and is the authoritative financial
record. Aggregate counters on `partners` exist for fast listing and are
never the source of truth for money.

```
pending ──(30-day hold elapses)──> payable ──(payout)──> paid
   │                                  │                    │
   └──────────> held ─────────────────┘                    │
                  └──────────────> reversed <──────────────┘
```

* Reversals are **new negative rows** referencing `reverses_id`. The
  original is never edited or deleted, so a partner's history stays
  legible and `SUM(amount_minor)` is always their true balance.
* A partial refund reverses proportionally at the original rate and leaves
  the original standing — some of it was genuinely earned.
* Reversing an already-*paid* commission is allowed; the negative entry is
  recovered from the next payout rather than being written off.
* Reversals land in the **current** period, so a closed month is never
  retroactively rewritten.
* Every status change writes a `partner_commission_events` row recording
  who or what moved it and why. Partners can read their own trail at
  `GET /v1/partners/me/commissions/{id}/events`.

**Idempotency is enforced by the database**, not by application code:
`uq_partner_commissions_idempotency` on
`(partner_id, entry_type, idempotency_key)` where the key is
`payment:{reference}:rel:{relationship_id}`. A replayed Paystack webhook, a
retried Celery task and a double-clicked verify button all converge on one
row.

Rates are **snapshotted** onto the relationship at creation. Changing
configuration or negotiating new terms affects future relationships only;
historical economics cannot shift underneath a partner.

Each entry stores a `calculation_basis` JSONB blob including the formula,
so any future reader can reconstruct exactly why a number was paid.

---

## 4. Payouts

Payouts extend the existing `PaystackClient` with transfer endpoints — there
is no second payment abstraction and no second billing system.

* **Amounts are derived, never supplied.** The total is summed from payable
  ledger rows locked `FOR UPDATE SKIP LOCKED` inside the transaction.
* **Idempotent in the database.** `uq_partner_payouts_idempotency` on
  `(partner_id, idempotency_key)`, plus a platform-wide unique constraint on
  `partner_payout_items.commission_id` so a commission physically cannot
  appear in two payouts. This matters because `IdempotencyMiddleware` fails
  open when Redis is unavailable.
* **Minimum threshold** of `PARTNER_MIN_PAYOUT_MINOR` (default $50).
* **One payout in flight** per partner at a time.
* **Failure returns the money.** A failed or cancelled payout writes a
  compensating `payout_reversal` entry restoring the payable balance, rather
  than rewriting the terminal `paid` status.
* The provider call uses our own payout reference, so a retry cannot create
  a second transfer.

Account details are Fernet-encrypted at rest via the platform's existing
`encrypt_jsonb`. Responses expose only a masked label and the last four
characters, and the raw number is never logged — not even at DEBUG.

---

## 5. Fraud review

The philosophy matters more than the arithmetic.

**Shared infrastructure is not evidence.** There is deliberately no same-IP
signal, and no rule treating a shared company domain, office, university,
coworking space or VPN as suspicious. Those patterns describe ordinary
customers, and punishing them would quietly destroy legitimate partnerships.
A test asserts that no such signal exists.

What is weighed is behaviour that costs money or that no honest partner
produces: self-referral (45), chargeback history (35), payment-instrument
reuse (30), high refund rate (25), zero-engagement conversions (20), rapid
churn (20), identity clustering (18), disposable email (15), velocity
anomalies (15), click flooding (10), unverified claims (10), geo mismatch
(5). Weights are additive and clamped to 100.

Every rule requires enough volume to be meaningful — flagging someone over
two data points is how you lose good partners.

Bands: 0–29 low, 30–59 medium, 60–79 high, 80–100 critical.

**Scores never act alone.** A high score *holds* commissions — the money
stays in the ledger, fully recoverable — and opens a flag for a human. No
score suspends a partner, bans a user or reverses money by itself. An admin
resolves each flag with an explicit action, and that action is *executed*,
not merely recorded, so a flag's stated outcome always matches reality.

---

## 6. Privacy and authorisation

* Referred-customer emails are masked at **every** tier
  (`j•••e@acme.com`). There is no unmasked variant for partners.
* No cross-partner access anywhere. Ownership is part of the SQL `WHERE`
  clause, not a post-hoc check, and unauthorised access returns **404** —
  the existence of another partner's resource is itself information.
* No endpoint accepts a client-supplied `partner_id`. The partner is always
  resolved server-side from the authenticated principal.
* Public directory listing is opt-in; unlisted partners return 404.
* Raw IPs are never stored. Clicks keep an HMAC keyed with `SECRET_KEY`,
  which still supports velocity analysis while being useless as a location.
* Duplicate-lead detection uses a keyed email hash and, when it rejects a
  submission, does not reveal which partner holds the claim.

---

## 7. Geo

Country-level only, from a local MaxMind GeoLite2 `.mmdb` read through
`maxminddb`. There is no per-request external GeoIP call. City, subdivision,
postcode and coordinates are available in the database and are deliberately
not extracted or stored.

A missing database degrades to "unknown" and logs once — geo is analytics
and must never be able to break a click. Lookups are cached in
`geo_ip_cache` keyed by hashed IP, negative results included.

`GET /v1/admin/geo/coverage` reports database age so a stale file is
visible.

---

## 8. Background jobs

On the existing Celery infrastructure (`app/modules/partners/tasks.py`), all
eight registered in `celery_app.beat_schedule`:

| Task | Schedule | Purpose |
|------|----------|---------|
| `commission_calculation` | every 6h | Safety net for commissions a lost webhook missed. Re-verifies with Paystack; never assumes an amount. |
| `commission_hold_release` | daily 01:15 | pending → payable once the hold elapses. Skips partners under review. |
| `commission_monthly_settlement` | 1st, 01:45 | Closes the previous month per partner. |
| `commission_reversal` | daily 02:30 | Expires Year-1 windows so accrual stops on time. |
| `referral_attribution_expiry` | daily 03:10 | Expires unconverted touches past the window. |
| `geo_aggregation` | daily 04:20 | Rolls yesterday's clicks/conversions into per-country daily rows. |
| `partner_tier_evaluation` | daily 05:00 | Recomputes earned tiers from ledger metrics. Promotion only. |
| `fraud_analysis` | daily 05:30 | Scores active partners, raises flags. |

Automatic **demotion is deliberately not implemented** — lowering a
partner's standing is a relationship decision, so it stays an explicit admin
action.

---

## 9. Tiers

`explorer → partner → certified → agency → strategic`, earned from active
customer count and lifetime revenue.

Tiers unlock **capabilities** (co-marketing, custom terms, dedicated
support). They are **never** a commission multiplier — rates are per method
and identical at every tier, which is what keeps the economics predictable.
The `agency` tier reflects a business relationship rather than volume, so
automation never assigns or removes it.

---

## 10. Configuration

All defaulted in `app/config.py` and mirrored in `.env.example`:

```
RELIASTRA_PUBLIC_URL=https://reliastra.com
PARTNER_REFERRAL_PATH_PREFIX=/r
PARTNER_ATTRIBUTION_WINDOW_DAYS=90
PARTNER_COMMISSION_HOLD_DAYS=30
PARTNER_DEFAULT_CURRENCY=USD
PARTNER_RATE_REFER_BPS=2000
PARTNER_RATE_DEPLOY_BPS=3000
PARTNER_RATE_CREATE_BPS=2500
PARTNER_RATE_INTRODUCE_BPS=1500
PARTNER_RATE_RESELL_BPS=0
PARTNER_MAX_TOTAL_COMMISSION_BPS=5000
PARTNER_INTRODUCE_WINDOW_MONTHS=12
PARTNER_MIN_PAYOUT_MINOR=5000
PARTNER_CLICK_DEDUP_WINDOW_SECONDS=1800
PARTNER_FRAUD_REVIEW_SCORE=70
PARTNER_AUTO_APPROVE_APPLICATIONS=false
MAXMIND_DB_PATH=/var/lib/geoip/GeoLite2-City.mmdb
MAXMIND_CACHE_TTL_SECONDS=86400
```

---

## 11. Layout

```
app/modules/partners/
  constants.py      Enums, state-transition graphs, fraud weights, tier rules
  economics.py      Pure commission arithmetic — no I/O, exhaustively tested
  links.py          ReferralLinkService: the only place a URL is built
  utils.py          Codes, keyed hashes, masking, bot heuristics
  models.py         22 tables
  repository.py     Ownership-scoped data access, static methods
  schemas.py        Request/response models
  service.py        Partner lifecycle, campaigns, links, leads, claims, tiers
  tracking.py       Clicks and attribution
  commissions.py    The ledger
  payouts.py        Payout lifecycle, extends PaystackClient
  fraud.py          Risk scoring and flag resolution
  geo.py            Local MaxMind lookups + cache
  tasks.py          The eight scheduled jobs
  router.py         /v1/partners/*
  public_router.py  /v1/public/*
  admin_router.py   /v1/admin/partners/*, /v1/admin/geo/*
```

Migration: `0016_partner_network` (additive; no existing table altered).

---

## 12. Rate limits

Link resolution is deliberately generous — 1200/min per IP. A launch
campaign or an email blast from one corporate NAT must not start 429-ing
real visitors. Validation probes get 600/min. Directory browsing, which can
enumerate, gets the standard public 60/min. Applications are 5/hour and
payout requests 10/hour per user.

---

## 13. Tests

```
tests/unit/test_partner_economics.py       31  commission arithmetic
tests/unit/test_partner_links.py           31  URL building, masking, hashing
tests/unit/test_partner_fraud_and_geo.py   33  scoring, geo, job registration
tests/integration/test_partners_api.py     82  full lifecycle + authorization
```

The integration suite includes an end-to-end test covering apply → approve →
code → link → campaign → click → attribution → signup → payment →
commission → hold → payable → payout → ledger → analytics, plus a dedicated
class asserting cross-partner denial on every ownership-scoped endpoint.

---

## 14. Frontend contract (`/partners`)

The public Partner Network page must consume **`GET /v1/partner-program`**.
The response includes live economics plus a `landing` object:

* `positioning` — hero copy, CTAs, canonical path `/partners`
* `how_it_works` — join → share → convert → earn
* `audiences` / `reasons` / `scenario` / `diagnostic`
* `faq` — visible DOM answers; use for FAQPage structured data
* `seo` — title, description, canonical
* `commission_illustration` — labelled **ILLUSTRATIVE EXAMPLE**; never treat as a payout
* `resources` — catalog; `available: false` means no file exists
* `frontend_endpoints` — the only paths the UI should call

Authenticated surfaces:

| UI | Endpoint |
|----|----------|
| Apply | `POST /v1/partners/apply` |
| Application status | `GET /v1/partners/applications` |
| Profile + referral URL | `GET /v1/partners/me` |
| Dashboard KPIs | `GET /v1/partners/me/dashboard` |
| Activity series | `GET /v1/partners/me/analytics` |
| Resource center | `GET /v1/partners/me/resources` |
| Ledger / balance | `GET /v1/partners/me/commissions`, `.../balance` |
| Customers | `GET /v1/partners/me/customers` (emails masked) |
| Link click | `GET /v1/referral/{partner_code}` |

Do not invent endpoints. Do not compute commission on the client. Do not
render private dashboard numbers in public HTML. White-label rebranding is
**not** a live API — the FAQ states this explicitly.
