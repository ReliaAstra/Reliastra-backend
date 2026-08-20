# Evidence report token lifecycle

## Generation

`POST /v1/evidence/gate` (formerly `/v1/public/evidence/gate`):

1. Validate the incident has a public evidence report.
2. Optionally auto-create a user/org for the lead email.
3. Generate `report_token = token_urlsafe(32)`.
4. Persist `SHA-256(report_token)` (never the raw token).
5. Set `expires_at = now + REPORT_TOKEN_TTL_DAYS` (**7 days**).

Response includes `report_token` and `expires_at`.

## Validation

`GET /v1/evidence/{report_token}/download`:

1. Hash the presented token and look up `evidence_gate_tokens.token_hash`.
2. Reject unknown hashes (`404`).
3. Reject `now > expires_at` (`422 VALIDATION_ERROR`).
4. Stream the PDF and mark the token downloaded (first use only).

Tokens are single-purpose download credentials. They are not JWTs and cannot
be used as session credentials.
