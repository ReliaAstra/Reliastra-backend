package database

import (
	"context"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/migrations"
)

// Migrator applies embedded migrations deterministically.
type Migrator struct {
	pool *pgxpool.Pool
}

// NewMigrator creates a migrator over the given pool.
func NewMigrator(pool *pgxpool.Pool) *Migrator { return &Migrator{pool: pool} }

// EnsureSchema creates the schema_migrations table if missing.
func (m *Migrator) EnsureSchema(ctx context.Context) error {
	_, err := m.pool.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (
		version    int PRIMARY KEY,
		name       text NOT NULL,
		applied_at timestamptz NOT NULL DEFAULT now()
	)`)
	return err
}

type appliedRow struct {
	Version   int
	Name      string
	AppliedAt time.Time
}

func (m *Migrator) applied(ctx context.Context) (map[int]appliedRow, error) {
	rows, err := m.pool.Query(ctx, `SELECT version, name, applied_at FROM schema_migrations ORDER BY version`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[int]appliedRow{}
	for rows.Next() {
		var r appliedRow
		if err := rows.Scan(&r.Version, &r.Name, &r.AppliedAt); err != nil {
			return nil, err
		}
		out[r.Version] = r
	}
	return out, rows.Err()
}

// Up applies all pending migrations in version order.
func (m *Migrator) Up(ctx context.Context) ([]int, error) {
	if err := m.EnsureSchema(ctx); err != nil {
		return nil, err
	}
	all, err := migrations.All()
	if err != nil {
		return nil, err
	}
	applied, err := m.applied(ctx)
	if err != nil {
		return nil, err
	}
	var appliedNow []int
	for _, mig := range all {
		if _, ok := applied[mig.Version]; ok {
			continue
		}
		if err := m.applyOne(ctx, mig.Up, mig.Version, mig.Name); err != nil {
			return appliedNow, fmt.Errorf("migrations: applying %04d_%s.up: %w", mig.Version, mig.Name, err)
		}
		appliedNow = append(appliedNow, mig.Version)
	}
	return appliedNow, nil
}

// Down rolls back the most recent migration. destVersion is exclusive.
func (m *Migrator) Down(ctx context.Context) error {
	if err := m.EnsureSchema(ctx); err != nil {
		return err
	}
	all, err := migrations.All()
	if err != nil {
		return err
	}
	applied, err := m.applied(ctx)
	if err != nil {
		return err
	}
	var appliedVersions []int
	for v := range applied {
		appliedVersions = append(appliedVersions, v)
	}
	if len(appliedVersions) == 0 {
		return nil
	}
	sort.Ints(appliedVersions)
	latest := appliedVersions[len(appliedVersions)-1]
	for _, mig := range all {
		if mig.Version == latest {
			if mig.Down == "" {
				return fmt.Errorf("migrations: no down migration for version %04d (%s)", mig.Version, mig.Name)
			}
			if err := m.applyOne(ctx, mig.Down, mig.Version, mig.Name); err != nil {
				return fmt.Errorf("migrations: applying %04d_%s.down: %w", mig.Version, mig.Name, err)
			}
			return nil
		}
	}
	return fmt.Errorf("migrations: version %d applied but not found in embedded files", latest)
}

// Status prints the current migration state.
func (m *Migrator) Status(ctx context.Context) ([]StatusRow, error) {
	if err := m.EnsureSchema(ctx); err != nil {
		return nil, err
	}
	all, err := migrations.All()
	if err != nil {
		return nil, err
	}
	applied, err := m.applied(ctx)
	if err != nil {
		return nil, err
	}
	var out []StatusRow
	for _, mig := range all {
		a, ok := applied[mig.Version]
		out = append(out, StatusRow{
			Version:   mig.Version,
			Name:      mig.Name,
			Applied:   ok,
			AppliedAt: a.AppliedAt,
		})
	}
	return out, nil
}

// StatusRow describes one migration's state.
type StatusRow struct {
	Version   int
	Name      string
	Applied   bool
	AppliedAt time.Time
}

func (m *Migrator) applyOne(ctx context.Context, sql string, version int, name string) error {
	tx, err := m.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after commit
	if _, err := tx.Exec(ctx, sql); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO schema_migrations (version, name) VALUES ($1, $2)`, version, name); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
