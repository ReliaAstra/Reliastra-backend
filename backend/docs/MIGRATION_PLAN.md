# Data migration plan

## Users without an organization

Registration has always created a default org. For any historical user with
zero memberships:

```sql
-- Preview
SELECT u.id, u.email
FROM users u
LEFT JOIN organization_members m ON m.user_id = u.id
WHERE m.id IS NULL;

-- Backfill (run in a transaction)
INSERT INTO organizations (id, name, slug, plan, created_at, updated_at)
SELECT gen_random_uuid(),
       COALESCE(u.full_name, 'User') || '''s Organization',
       'org-' || substr(replace(u.id::text, '-', ''), 1, 8),
       'free',
       now(),
       now()
FROM users u
LEFT JOIN organization_members m ON m.user_id = u.id
WHERE m.id IS NULL;

INSERT INTO organization_members (id, org_id, user_id, role, joined_at)
SELECT gen_random_uuid(), o.id, u.id, 'owner', now()
FROM users u
JOIN organizations o ON o.slug = 'org-' || substr(replace(u.id::text, '-', ''), 1, 8)
LEFT JOIN organization_members m ON m.user_id = u.id
WHERE m.id IS NULL;
```

No URL-stored org IDs exist in the database; this is an API-only change.

## Evidence gate tokens

Existing tokens keep their stored `expires_at`. New tokens use a 7-day TTL
(`REPORT_TOKEN_TTL_DAYS`). No table change is required.

## Client rollout

1. Ship frontend/SDK that reads `register.tokens` and sends `X-Organization-ID`.
2. Deploy this API.
3. Remove leftover `/v1/orgs/{id}/...` and `/v1/public/...` callers.
