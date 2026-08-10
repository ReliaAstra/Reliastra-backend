// Package regions models geographically independent observation regions.
// Regions are data-driven: adding a region requires configuration, not code.
package regions

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Region is an observation region.
type Region struct {
	ID           string         `json:"id"`
	Name         string         `json:"name"`
	Slug         string         `json:"slug"`
	Country      string         `json:"country"`
	Provider     string         `json:"provider"`
	Status       string         `json:"status"`
	Capabilities []string       `json:"capabilities"`
	CreatedAt    time.Time      `json:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at"`
}

// Store persists regions.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const cols = `id, name, slug, country, provider, status, capabilities, created_at, updated_at`

func scan(row pgx.Row) (*Region, error) {
	var r Region
	var caps []byte
	err := row.Scan(&r.ID, &r.Name, &r.Slug, &r.Country, &r.Provider, &r.Status, &caps, &r.CreatedAt, &r.UpdatedAt)
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(caps, &r.Capabilities)
	return &r, nil
}

// Create inserts a region (admin/seed operation).
func (s *Store) Create(ctx context.Context, r *Region) (*Region, error) {
	r.ID = ids.NewUUID()
	caps, _ := json.Marshal(r.Capabilities)
	_, err := s.pool.Exec(ctx, `INSERT INTO regions (id, name, slug, country, provider, status, capabilities)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`, r.ID, r.Name, r.Slug, r.Country, r.Provider, r.Status, string(caps))
	if err != nil {
		return nil, err
	}
	return r, nil
}

// List returns all regions.
func (s *Store) List(ctx context.Context) ([]Region, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+cols+` FROM regions ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Region
	for rows.Next() {
		r, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *r)
	}
	return out, rows.Err()
}

// Active returns active regions only.
func (s *Store) Active(ctx context.Context) ([]Region, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+cols+` FROM regions WHERE status='active' ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Region
	for rows.Next() {
		r, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *r)
	}
	return out, rows.Err()
}
