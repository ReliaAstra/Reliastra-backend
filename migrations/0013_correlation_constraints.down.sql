ALTER TABLE incident_correlations DROP CONSTRAINT IF EXISTS incident_correlations_confidence_check;
ALTER TABLE incident_correlations ADD CONSTRAINT incident_correlations_confidence_check
    CHECK (confidence IN ('low', 'medium', 'high'));

DROP INDEX IF EXISTS incidents_open_target_idx;
CREATE UNIQUE INDEX incidents_open_target_idx
    ON incidents (service_id, dependency_id)
    WHERE status IN ('candidate', 'investigating', 'confirmed');
