-- 0011_scheduling: per-monitor scheduling state and region assignment.
-- The scheduler maintains next_run_at so due-monitor queries are a cheap
-- index range scan instead of an aggregate over the entire job history.

ALTER TABLE monitors ADD COLUMN IF NOT EXISTS next_run_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS monitors_due_idx ON monitors (enabled, status, next_run_at);

-- A monitor observes from one or more regions. One check job is created per
-- (monitor, region) per scheduled time.
CREATE TABLE IF NOT EXISTS monitor_regions (
    monitor_id uuid NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    region_id  uuid NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (monitor_id, region_id)
);
CREATE INDEX IF NOT EXISTS monitor_regions_region_idx ON monitor_regions (region_id);
