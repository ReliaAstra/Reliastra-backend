package checks

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Target types.
const (
	TargetService    = "service"
	TargetDependency = "dependency"
	TargetPublic     = "public"
)

// Observation is a normalized observation of a target from a region at a
// point in time. Correlation and the incident engine operate on these, never
// on raw HTTP details.
type Observation struct {
	ID             string         `json:"id"`
	TargetType     string         `json:"target_type"`
	TargetID       string         `json:"target_id"`
	MonitorID      string         `json:"monitor_id"`
	RegionID       string         `json:"region_id"`
	OrganizationID string         `json:"organization_id,omitempty"`
	ObservedAt     time.Time      `json:"observed_at"`
	Availability   bool           `json:"availability"`
	LatencyMS      int            `json:"latency_ms"`
	Status         string         `json:"status"` // ok | degraded | down
	FailureClass   string         `json:"failure_class,omitempty"`
	Metadata       map[string]any `json:"metadata,omitempty"`
	CreatedAt      time.Time      `json:"created_at"`
}

// ObservationStore persists and queries normalized observations.
type ObservationStore struct {
	pool *pgxpool.Pool
}

// NewObservationStore builds an ObservationStore.
func NewObservationStore(pool *pgxpool.Pool) *ObservationStore {
	return &ObservationStore{pool: pool}
}

// Insert writes an observation on tx (same transaction as result + job).
func (s *ObservationStore) Insert(ctx context.Context, tx pgx.Tx, o *Observation) error {
	if o.ID == "" {
		o.ID = ids.NewUUID()
	}
	if o.Metadata == nil {
		o.Metadata = map[string]any{}
	}
	meta, err := json.Marshal(o.Metadata)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `INSERT INTO observations
		(id, target_type, target_id, monitor_id, region_id, organization_id, observed_at,
		 availability, latency_ms, status, failure_class, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
		o.ID, o.TargetType, o.TargetID, o.MonitorID, o.RegionID, nullableOrg(o.OrganizationID),
		o.ObservedAt, o.Availability, o.LatencyMS, o.Status, o.FailureClass, string(meta))
	return err
}

// RecentForTarget returns observations for a target within [from, to],
// newest first, bounded by limit.
func (s *ObservationStore) RecentForTarget(ctx context.Context, targetType, targetID string, from, to time.Time, limit int) ([]Observation, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, target_type, target_id, monitor_id, region_id, organization_id, observed_at,
		       availability, latency_ms, status, failure_class, metadata, created_at
		FROM observations
		WHERE target_type=$1 AND target_id=$2 AND observed_at >= $3 AND observed_at <= $4
		ORDER BY observed_at DESC
		LIMIT $5`, targetType, targetID, from, to, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanObservations(rows)
}

// RecentForTargets returns observations for multiple target ids (correlation).
func (s *ObservationStore) RecentForTargets(ctx context.Context, targetType string, targetIDs []string, from, to time.Time, limit int) (map[string][]Observation, error) {
	out := map[string][]Observation{}
	for _, id := range targetIDs {
		obs, err := s.RecentForTarget(ctx, targetType, id, from, to, limit)
		if err != nil {
			return nil, err
		}
		out[id] = obs
	}
	return out, nil
}

func scanObservations(rows pgx.Rows) ([]Observation, error) {
	var out []Observation
	for rows.Next() {
		var o Observation
		var meta []byte
		if err := rows.Scan(&o.ID, &o.TargetType, &o.TargetID, &o.MonitorID, &o.RegionID,
			&o.OrganizationID, &o.ObservedAt, &o.Availability, &o.LatencyMS, &o.Status,
			&o.FailureClass, &meta, &o.CreatedAt); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(meta, &o.Metadata)
		out = append(out, o)
	}
	return out, rows.Err()
}

func nullableOrg(orgID string) any {
	if orgID == "" {
		return nil
	}
	return orgID
}
