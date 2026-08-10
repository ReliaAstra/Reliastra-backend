-- 0013_correlation_constraints: allow 'none' confidence in correlation rows.
-- The rule-based correlator returns confidence 'none' when no dependency
-- clears the low threshold; that is a valid, explainable outcome.

ALTER TABLE incident_correlations DROP CONSTRAINT IF EXISTS incident_correlations_confidence_check;
ALTER TABLE incident_correlations ADD CONSTRAINT incident_correlations_confidence_check
    CHECK (confidence IN ('low', 'medium', 'high', 'none'));

-- One open incident per target: the original partial unique index treated
-- NULLs as distinct, so dependency-only incidents (dependency_id set,
-- service_id NULL) were never deduplicated. NULLS NOT DISTINCT (PG 15+)
-- makes (service_id, dependency_id) match on NULLs too.
DROP INDEX IF EXISTS incidents_open_target_idx;
CREATE UNIQUE INDEX incidents_open_target_idx
    ON incidents (service_id, dependency_id) NULLS NOT DISTINCT
    WHERE status IN ('candidate', 'investigating', 'confirmed');
