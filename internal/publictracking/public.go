// Package publictracking implements the public vendor catalog and the
// strictly-separated public observation store. Public data never carries
// customer identifiers: no customer URLs, headers, credentials, incident
// details or service names.
package publictracking

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Vendor is a global catalog entry.
type Vendor struct {
	ID            string    `json:"id"`
	Slug          string    `json:"slug"`
	Name          string    `json:"name"`
	Provider      string    `json:"provider"`
	Category      string    `json:"category"`
	Description   string    `json:"description"`
	PublicEnabled bool      `json:"public_enabled"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// Store persists vendors and public observations.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds the Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// UpsertVendor inserts or updates a vendor catalog entry.
func (s *Store) UpsertVendor(ctx context.Context, v *Vendor) (*Vendor, error) {
	if v.ID == "" {
		v.ID = ids.NewUUID()
	}
	_, err := s.pool.Exec(ctx, `INSERT INTO vendors
		(id, slug, name, provider, category, description, public_enabled)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name, provider=EXCLUDED.provider,
			category=EXCLUDED.category, description=EXCLUDED.description,
			public_enabled=EXCLUDED.public_enabled, updated_at=now()`,
		v.ID, v.Slug, v.Name, v.Provider, v.Category, v.Description, v.PublicEnabled)
	if err != nil {
		return nil, err
	}
	return v, nil
}

// ListVendors returns enabled vendors (public API).
func (s *Store) ListVendors(ctx context.Context) ([]Vendor, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, slug, name, provider, category, description,
		public_enabled, created_at, updated_at FROM vendors
		WHERE public_enabled = true ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Vendor
	for rows.Next() {
		var v Vendor
		if err := rows.Scan(&v.ID, &v.Slug, &v.Name, &v.Provider, &v.Category, &v.Description,
			&v.PublicEnabled, &v.CreatedAt, &v.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, rows.Err()
}

// VendorBySlug returns one vendor.
func (s *Store) VendorBySlug(ctx context.Context, slug string) (*Vendor, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, slug, name, provider, category, description,
		public_enabled, created_at, updated_at FROM vendors WHERE slug=$1`, slug)
	var v Vendor
	err := row.Scan(&v.ID, &v.Slug, &v.Name, &v.Provider, &v.Category, &v.Description,
		&v.PublicEnabled, &v.CreatedAt, &v.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("vendor_not_found", "vendor not found")
	}
	if err != nil {
		return nil, err
	}
	return &v, nil
}

// RecordPublicObservation writes one public observation (called by workers
// for public monitors) on the caller's transaction.
func (s *Store) RecordPublicObservation(ctx context.Context, tx pgx.Tx, monitorID, regionID, vendorID string, obs *checks.Observation) error {
	_, err := tx.Exec(ctx, `INSERT INTO public_observations
		(id, vendor_id, region_id, monitor_id, observed_at, availability, latency_ms, failure_class)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		ids.NewUUID(), vendorID, regionID, monitorID, obs.ObservedAt,
		obs.Availability, obs.LatencyMS, obs.FailureClass)
	return err
}

// PublicSeries is a time-bucketed series for public charts.
type PublicSeries struct {
	VendorID     string    `json:"vendor_id"`
	RegionID     string    `json:"region_id,omitempty"`
	Bucket       time.Time `json:"bucket"`
	Availability float64   `json:"availability"`
	AvgLatencyMS float64   `json:"avg_latency_ms"`
	Observations int       `json:"observations"`
}

// Series returns public observations aggregated per bucket (default 1 hour)
// for a vendor. Only aggregate availability/latency are exposed — never raw
// targets or customer data.
func (s *Store) Series(ctx context.Context, vendorID string, from, to time.Time, bucketSec int) ([]PublicSeries, error) {
	if bucketSec <= 0 {
		bucketSec = 3600
	}
	rows, err := s.pool.Query(ctx, `
		SELECT date_trunc('second', to_timestamp(floor(extract(epoch from observed_at) / $1) * $1)) AS bucket,
		       region_id,
		       round(avg(availability::int)::numeric, 4) AS availability,
		       round(avg(latency_ms)::numeric, 1) AS latency,
		       count(*) AS observations
		FROM public_observations
		WHERE vendor_id=$2 AND observed_at >= $3 AND observed_at <= $4
		GROUP BY bucket, region_id
		ORDER BY bucket`, bucketSec, vendorID, from, to)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []PublicSeries
	for rows.Next() {
		var p PublicSeries
		var availability, latency float64
		if err := rows.Scan(&p.Bucket, &p.RegionID, &availability, &latency, &p.Observations); err != nil {
			return nil, err
		}
		p.VendorID = vendorID
		p.Availability = availability
		p.AvgLatencyMS = latency
		out = append(out, p)
	}
	return out, rows.Err()
}

// VendorStatus returns the aggregate availability/latency over a window.
func (s *Store) VendorStatus(ctx context.Context, vendorID string, window time.Duration) (map[string]any, error) {
	row := s.pool.QueryRow(ctx, `
		SELECT round(avg(availability::int)::numeric,4), round(avg(latency_ms)::numeric,1), count(*)
		FROM public_observations WHERE vendor_id=$1 AND observed_at >= now() - $2`,
		vendorID, window)
	var availability, latency float64
	var count int64
	if err := row.Scan(&availability, &latency, &count); err != nil {
		return nil, err
	}
	out := map[string]any{
		"vendor_id":    vendorID,
		"window":       window.String(),
		"availability": availability,
		"avg_latency_ms": latency,
		"observations": count,
	}
	return out, nil
}

var _ = json.Marshal
