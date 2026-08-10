package billing

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// DBCounter implements UsageCounter against PostgreSQL.
type DBCounter struct {
	pool *pgxpool.Pool
}

// NewDBCounter builds the counter.
func NewDBCounter(pool *pgxpool.Pool) *DBCounter { return &DBCounter{pool: pool} }

// CountMonitors implements UsageCounter.
func (c *DBCounter) CountMonitors(ctx context.Context, orgID string) (int, error) {
	return c.count(ctx, `SELECT count(*) FROM monitors WHERE organization_id=$1 AND visibility='customer'`, orgID)
}

// CountProjects implements UsageCounter.
func (c *DBCounter) CountProjects(ctx context.Context, orgID string) (int, error) {
	return c.count(ctx, `SELECT count(*) FROM projects WHERE organization_id=$1`, orgID)
}

// CountMembers implements UsageCounter.
func (c *DBCounter) CountMembers(ctx context.Context, orgID string) (int, error) {
	return c.count(ctx, `SELECT count(*) FROM organization_members WHERE organization_id=$1`, orgID)
}

// CountAPIKeys implements UsageCounter.
func (c *DBCounter) CountAPIKeys(ctx context.Context, orgID string) (int, error) {
	return c.count(ctx, `SELECT count(*) FROM api_keys WHERE organization_id=$1 AND status='active'`, orgID)
}

// CountEvidenceToday implements UsageCounter.
func (c *DBCounter) CountEvidenceToday(ctx context.Context, orgID string) (int, error) {
	return c.count(ctx, `SELECT count(*) FROM evidence_records er
		JOIN incidents i ON i.id = er.incident_id
		WHERE i.organization_id=$1 AND er.generated_at >= date_trunc('day', now())`, orgID)
}

func (c *DBCounter) count(ctx context.Context, q string, orgID string) (int, error) {
	var n int
	err := c.pool.QueryRow(ctx, q, orgID).Scan(&n)
	return n, err
}
