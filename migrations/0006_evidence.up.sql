-- 0006_evidence: immutable evidence records.
-- Finalized evidence is written once: canonical JSON + PDF in object storage,
-- hash recorded here. Never updated in place; changes create new versions.

CREATE TABLE IF NOT EXISTS evidence_records (
    id                  uuid PRIMARY KEY,
    incident_id         uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    version             int NOT NULL DEFAULT 1,
    status              text NOT NULL DEFAULT 'generating'
                       CHECK (status IN ('generating', 'finalized', 'failed')),
    generated_at        timestamptz,
    methodology_version text NOT NULL,
    hash_algorithm      text NOT NULL DEFAULT 'sha256',
    hash                text NOT NULL DEFAULT '',
    storage_key         text NOT NULL DEFAULT '',
    size_bytes          bigint NOT NULL DEFAULT 0,
    failure_reason      text NOT NULL DEFAULT '',
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (incident_id, version)
);
CREATE INDEX IF NOT EXISTS evidence_records_incident_idx ON evidence_records (incident_id, version);
