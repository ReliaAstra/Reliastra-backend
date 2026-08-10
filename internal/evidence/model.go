// Package evidence implements the evidence engine: immutable evidence
// records, canonical serialization, SHA-256 integrity, PDF reports and
// verification. Evidence is durable by design: finalized artifacts are never
// modified in place; changes create new versions.
package evidence

import (
	"time"
)

// Evidence statuses.
const (
	StatusGenerating = "generating"
	StatusFinalized  = "finalized"
	StatusFailed     = "failed"
)

// EvidenceRecord is a persisted evidence record row.
type EvidenceRecord struct {
	ID                  string     `json:"id"`
	IncidentID          string     `json:"incident_id"`
	Version             int        `json:"version"`
	Status              string     `json:"status"`
	GeneratedAt         *time.Time `json:"generated_at,omitempty"`
	MethodologyVersion  string     `json:"methodology_version"`
	HashAlgorithm       string     `json:"hash_algorithm"`
	Hash                string     `json:"hash,omitempty"`
	StorageKey          string     `json:"storage_key,omitempty"`
	SizeBytes           int64      `json:"size_bytes,omitempty"`
	FailureReason       string     `json:"failure_reason,omitempty"`
	CreatedAt           time.Time  `json:"created_at"`
}

// Canonical evidence document. Field order is fixed so json.Marshal output is
// deterministic: the stored artifact bytes equal the hashed bytes.
type Package struct {
	SchemaVersion        string             `json:"schema_version"`
	EvidenceID           string             `json:"evidence_id"`
	Version              int                `json:"version"`
	MethodologyVersion   string             `json:"methodology_version"`
	CorrelationAlgorithmVersion string        `json:"correlation_algorithm_version"`
	ScoringConfigVersion string             `json:"scoring_config_version"`
	GeneratedAt          string             `json:"generated_at"`

	Incident IncidentSection  `json:"incident"`
	Project  NameRef          `json:"project"`
	Service  *NameRef         `json:"service,omitempty"`
	Dependency *NameRef       `json:"dependency,omitempty"`

	Attribution *AttributionSection `json:"attribution,omitempty"`

	Timeline     []TimelineEntry   `json:"timeline"`
	Measurements MeasurementsSection `json:"measurements"`
	Regions      []RegionSection   `json:"regions"`

	// Raw evidence references (observation ids).
	ObservationIDs []string `json:"observation_ids"`
	// Monitor configuration snapshots so historical evidence stays
	// interpretable after config changes.
	MonitorSnapshots []MonitorSnapshot `json:"monitor_snapshots"`

	Integrity IntegritySection `json:"integrity"`
}

// IncidentSection identifies the incident.
type IncidentSection struct {
	ID        string `json:"id"`
	Number    string `json:"number"`
	Status    string `json:"status"`
	Severity  string `json:"severity"`
	Title     string `json:"title"`
	Summary   string `json:"summary"`
	StartedAt string `json:"started_at"`
	DetectedAt string `json:"detected_at"`
	ResolvedAt string `json:"resolved_at,omitempty"`
}

// NameRef references a named entity (project/service/dependency).
type NameRef struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

// AttributionSection is the deterministic correlation conclusion.
type AttributionSection struct {
	DependencyID   string            `json:"dependency_id"`
	DependencyName string            `json:"dependency_name"`
	Confidence     string            `json:"confidence"`
	EvidenceScore  float64           `json:"evidence_score"`
	Factors        map[string]float64 `json:"factors"`
	Explanations   []string          `json:"explanations"`
}

// TimelineEntry is one timestamped event.
type TimelineEntry struct {
	At        string `json:"at"`
	Event     string `json:"event"`
	Detail    string `json:"detail,omitempty"`
}

// MeasurementsSection aggregates observed behavior.
type MeasurementsSection struct {
	Availability  map[string]float64 `json:"availability"`
	AvgLatencyMS  map[string]float64 `json:"avg_latency_ms"`
	StatusCodes   map[string]int     `json:"status_codes"`
	ErrorClasses  map[string]int     `json:"error_classes"`
	TotalObservations int           `json:"total_observations"`
}

// RegionSection is the per-region outcome.
type RegionSection struct {
	RegionID     string  `json:"region_id"`
	RegionName   string  `json:"region_name"`
	Observations int     `json:"observations"`
	Failed       int     `json:"failed"`
	Availability float64 `json:"availability"`
}

// MonitorSnapshot preserves the monitor configuration used for the evidence.
type MonitorSnapshot struct {
	MonitorID        string `json:"monitor_id"`
	Name             string `json:"name"`
	Type             string `json:"type"`
	Target           string `json:"target"`
	IntervalSeconds  int    `json:"interval_seconds"`
	TimeoutSeconds   int    `json:"timeout_seconds"`
	ConfigurationSHA string `json:"configuration_sha"` // hash of config; no secrets
}

// IntegritySection declares the integrity scheme used by the artifact. The
// authoritative digest is stored in evidence_records.
type IntegritySection struct {
	HashAlgorithm string `json:"hash_algorithm"`
}
