# Security model and threat model

## Assets

1. Customer monitoring data (targets, credentials, incidents, evidence)
2. User accounts and session tokens
3. API keys (scoped, hashed)
4. The monitoring engine itself (SSRF surface)
5. Infrastructure (PostgreSQL, Redis, object storage)

## Threats and controls

| # | Threat | Control |
|---|---|---|
| T1 | Attacker reads another tenant's data (IDOR / cross-tenant) | Every query scopes by `organization_id`; resource lookups validate ownership through `projects`; `X-Reliasorg` header + membership check; API keys bound to one org. Automated IDOR tests. |
| T2 | Privilege escalation (member → admin) | Role checks at the service layer (`owner`/`admin` only for API keys, etc.); org membership is the gate. |
| T3 | Authentication bypass | Bearer sessions with random 256-bit tokens (SHA-256 at rest); argon2id password hashing (per-password salt, configurable cost); constant-time comparison; uniform login errors. |
| T4 | API key theft | Keys shown once at creation; hashed at rest; revocable; scoped; prefix-based routing; rate limited per key. |
| T5 | Secrets leak (monitor headers/bodies) | Envelope encryption (AES-256-GCM, HKDF-derived per-record keys, `ciphertext|key_version|nonce`); redacted `<redacted>` placeholders in stored/returned configs; secrets never logged; redaction helpers on log fields. |
| T6 | SSRF from monitored URLs | Parse-time scheme/host validation; **dial-time re-resolution + validation** (defeats DNS rebinding); redirect re-validation per hop; blocked CIDR list (loopback, RFC1918, link-local, metadata 169.254.169.254, multicast, etc.); no userinfo in URLs; bounded redirects and bodies. |
| T7 | DoS via abusive monitor workload | Plan quotas (monitors, interval floor, members, projects, API keys, evidence/day); org-fair worker concurrency; bounded worker concurrency, response size, execution time; rate limiting (IP/user/org/key) via Redis; request size limits. |
| T8 | Replay of idempotent operations | `Idempotency-Key` handling for evidence generation and monitor creation; unique constraints make duplicates no-ops. |
| T9 | Tampered evidence | SHA-256 of canonical artifact recorded in PostgreSQL; `verify` endpoint re-hashes; immutable finalized records. |
| T10 | Audit trail forgery | `audit_logs` append-only (no API update/delete path). |
| T11 | Public data leakage through tracking pages | Public observations stored in a separate table, never joined with customer data; public API returns only catalog + aggregates; `public_enabled` gate. |
| T12 | Log/observability leakage | Structured JSON logs with secret-field redaction; request-scoped fields; no stack traces to clients; typed error envelope. |
| T13 | SQL injection | All queries parameterized (pgx); no string interpolation of user input. |
| T14 | Session fixation/replay | Sessions revoked on logout; expiry enforced; tokens opaque + high entropy. |

## SSRF defense in depth

1. **Parse-time** (`validateURL`): scheme must be http/https; no userinfo;
   host required.
2. **Dial-time** (`safeDialer`): resolve the hostname *at dial time* and
   reject any address in the blocked CIDR set. This is the authoritative gate
   and defeats DNS rebinding, decimal/hex/encoded IP tricks (they normalize
   to the same `netip.Addr`), and IPv4-mapped-IPv6 tricks (unmapped before
   checking).
3. **Redirect-time**: every redirect destination is re-parsed and
   re-validated; redirects are bounded.
4. Blocked ranges include `0.0.0.0/8`, `10/8`, `100.64/10`, `127/8`,
   `169.254/16`, `172.16/12`, `192.0.0/24`, `192.0.2/24`, `192.168/16`,
   `198.18/15`, `198.51.100/24`, `203.0.113/24`, multicast, reserved,
   `::1`, `fc00::/7`, `fe80::/10`, `64:ff9b::/96`, `2001:db8::/32`, etc.

## API hardening

- Security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Cache-Control: no-store`).
- CORS with explicit origin allowlist.
- Request body limits (`MaxBodyBytes`), header limits.
- Rate limits per scope (auth endpoints stricter).
- Error envelope: `code`, `message`, `request_id`, `details` — never stack
  traces or raw DB errors.
- Structured audit logging on mutating actions with actor, IP, user agent.

## Dependencies

Pinned versions in `go.mod`; third-party libraries are minimal and justified
(pgx, go-redis, minio-go, fpdf, client_golang, x/crypto). Network-restricted
mirrors are documented in `go.mod` replace directives; run `go vet` and a
vulnerability scanner (`govulncheck`) in CI.
