package incidents

import (
	"context"
	"time"
)

// CorrelationResult is the full per-dependency correlation output. Defined
// here (not in internal/correlation) so the incident detector can depend on
// the interface without a package cycle; the rule-based engine in
// internal/correlation implements Correlator.
type CorrelationResult struct {
	IncidentID            string    `json:"incident_id"`
	DependencyID          string    `json:"dependency_id"`
	CorrelationVersion    string    `json:"correlation_version"`
	ScoringConfigVersion  string    `json:"scoring_config_version"`
	EvidenceScore         float64   `json:"evidence_score"`
	Confidence            string    `json:"confidence"`
	TemporalOverlap       float64   `json:"temporal_overlap"`
	RegionalOverlap       float64   `json:"regional_overlap"`
	LatencySimilarity     float64   `json:"latency_similarity"`
	ErrorSimilarity       float64   `json:"error_similarity"`
	FailureOverlap        float64   `json:"failure_overlap"`
	CriticalityWeight     float64   `json:"criticality_weight"`
	ServiceFailureRate    float64   `json:"service_failure_rate"`
	DependencyFailureRate float64   `json:"dependency_failure_rate"`
	Explanations          []string  `json:"explanations"`
	WindowStart           time.Time `json:"window_start"`
	WindowEnd             time.Time `json:"window_end"`
}

// Correlator is the substitution boundary for future correlation
// implementations (statistical, ML, hybrid). The incident engine depends on
// this interface, never on a concrete engine.
type Correlator interface {
	// Run correlates a service incident against its linked dependencies and
	// returns per-dependency results, most likely first.
	Run(ctx context.Context, inc *Incident) ([]CorrelationResult, error)
}
