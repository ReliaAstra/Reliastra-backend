-- 0009_public: global vendor catalog and public observations.
-- Public observations are strictly separated from customer observations;
-- they never carry customer identifiers.

CREATE TABLE IF NOT EXISTS vendors (
    id            uuid PRIMARY KEY,
    slug          text NOT NULL,
    name          text NOT NULL,
    provider      text NOT NULL DEFAULT '',
    category      text NOT NULL DEFAULT 'other',
    description   text NOT NULL DEFAULT '',
    public_enabled boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS public_observations (
    id            uuid PRIMARY KEY,
    vendor_id     uuid NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    region_id     uuid NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    monitor_id    uuid NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    observed_at   timestamptz NOT NULL,
    availability  boolean NOT NULL,
    latency_ms    int NOT NULL DEFAULT 0,
    failure_class text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS public_observations_vendor_idx ON public_observations (vendor_id, observed_at DESC);
