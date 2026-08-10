-- 0007_notifications: transactional outbox, channels, deliveries.

-- Outbox: any important event is written in the same transaction as the
-- domain change it describes. The notifier consumes it asynchronously.
CREATE TABLE IF NOT EXISTS outbox_events (
    id              uuid PRIMARY KEY,
    event_type      text NOT NULL,
    aggregate_type  text NOT NULL DEFAULT '',
    aggregate_id    text NOT NULL DEFAULT '',
    organization_id uuid,
    payload         jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'processed', 'dead')),
    attempt         int NOT NULL DEFAULT 0,
    available_after timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_events_pending_idx ON outbox_events (status, available_after, created_at) WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS outbox_events_org_idx ON outbox_events (organization_id);

CREATE TABLE IF NOT EXISTS notification_channels (
    id              uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    type            text NOT NULL CHECK (type IN ('email', 'slack')),
    name            text NOT NULL,
    -- Envelope-encrypted channel config (e.g. email address, webhook URL).
    config_encrypted bytea NOT NULL,
    key_version     int NOT NULL DEFAULT 1,
    nonce           bytea NOT NULL,
    enabled         boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notification_channels_org_idx ON notification_channels (organization_id);

-- Delivery records are idempotent per (event, channel): unique constraint
-- makes duplicate outbox consumption harmless.
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id              uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event_id        uuid NOT NULL,
    channel_id      uuid NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
    event_type      text NOT NULL,
    status          text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'retrying', 'dead_letter')),
    attempt         int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error      text NOT NULL DEFAULT '',
    sent_at         timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, channel_id)
);
CREATE INDEX IF NOT EXISTS notification_deliveries_pending_idx ON notification_deliveries (status, next_attempt_at) WHERE status IN ('pending', 'retrying');
