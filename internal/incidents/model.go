// Package incidents implements the incident engine: durable incidents, an
// explicit state machine, and a deterministic rule-based detector. There is
// no AI in the attribution path (see internal/correlation).
package incidents

import (
	"time"
)

// Incident statuses.
const (
	StatusCandidate     = "candidate"
	StatusInvestigating = "investigating"
	StatusConfirmed     = "confirmed"
	StatusResolved      = "resolved"
	StatusFalsePositive = "false_positive"
)

// Severities.
const (
	SeverityLow      = "low"
	SeverityMedium   = "medium"
	SeverityHigh     = "high"
	SeverityCritical = "critical"
)

// Incident is a durable incident record.
type Incident struct {
	ID                       string    `json:"id"`
	Number                   string    `json:"number"`
	ProjectID                string    `json:"project_id"`
	OrganizationID           string    `json:"organization_id"`
	ServiceID                string    `json:"service_id,omitempty"`
	DependencyID             string    `json:"dependency_id,omitempty"`
	Status                   string    `json:"status"`
	Severity                 string    `json:"severity"`
	StartedAt                time.Time `json:"started_at"`
	DetectedAt               time.Time `json:"detected_at"`
	ResolvedAt               *time.Time `json:"resolved_at,omitempty"`
	Title                    string    `json:"title"`
	Summary                  string    `json:"summary"`
	AttributedDependencyID   string    `json:"attributed_dependency_id,omitempty"`
	Confidence               string    `json:"confidence"`
	EvidenceScore            float64   `json:"evidence_score"`
	CorrelationVersion       string    `json:"correlation_version,omitempty"`
	CreatedAt                time.Time `json:"created_at"`
	UpdatedAt                time.Time `json:"updated_at"`
}

// IncidentEvent is one auditable state transition.
type IncidentEvent struct {
	ID          string    `json:"id"`
	IncidentID  string    `json:"incident_id"`
	FromStatus  string    `json:"from_status"`
	ToStatus    string    `json:"to_status"`
	Reason      string    `json:"reason"`
	ActorType   string    `json:"actor_type"`
	ActorID     string    `json:"actor_id"`
	Metadata    map[string]any `json:"metadata,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
}
