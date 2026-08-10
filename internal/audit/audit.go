// Package audit implements the append-only audit log. Records are written
// through this package only; there is no update/delete path in the API.
package audit

import (
	"context"
	"encoding/json"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Record is one audit log entry.
type Record struct {
	ID             string         `json:"id"`
	OrganizationID string         `json:"organization_id,omitempty"`
	ActorID        string         `json:"actor_id,omitempty"`
	ActorType      string         `json:"actor_type"` // user | api_key | system
	Action         string         `json:"action"`
	ResourceType   string         `json:"resource_type,omitempty"`
	ResourceID     string         `json:"resource_id,omitempty"`
	Metadata       map[string]any `json:"metadata,omitempty"`
	IPAddress      string         `json:"ip_address,omitempty"`
	UserAgent      string         `json:"user_agent,omitempty"`
	CreatedAt      string         `json:"created_at"`
}

// Store persists audit records.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds the Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// Write inserts an audit record (outside any transaction boundary when nil).
func (s *Store) Write(ctx context.Context, r Record) error {
	meta, err := json.Marshal(r.Metadata)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO audit_logs
		(id, organization_id, actor_id, actor_type, action, resource_type, resource_id,
		 metadata, ip_address, user_agent)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		ids.NewUUID(), nullable(r.OrganizationID), r.ActorID, r.ActorType, r.Action,
		r.ResourceType, r.ResourceID, string(meta), r.IPAddress, r.UserAgent)
	return err
}

// List returns audit records for an org, newest first.
func (s *Store) List(ctx context.Context, orgID string, limit, offset int) ([]Record, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	rows, err := s.pool.Query(ctx, `SELECT id, organization_id, actor_id, actor_type, action,
		resource_type, resource_id, metadata, ip_address, user_agent, created_at
		FROM audit_logs WHERE organization_id=$1 ORDER BY created_at DESC LIMIT $2 OFFSET $3`,
		orgID, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Record
	for rows.Next() {
		var r Record
		var meta []byte
		var created string
		if err := rows.Scan(&r.ID, &r.OrganizationID, &r.ActorID, &r.ActorType, &r.Action,
			&r.ResourceType, &r.ResourceID, &meta, &r.IPAddress, &r.UserAgent, &created); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(meta, &r.Metadata)
		r.CreatedAt = created
		out = append(out, r)
	}
	return out, rows.Err()
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}
