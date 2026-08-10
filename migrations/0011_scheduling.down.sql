DROP TABLE IF EXISTS monitor_regions;
ALTER TABLE monitors DROP COLUMN IF EXISTS next_run_at;
DROP INDEX IF EXISTS monitors_due_idx;
