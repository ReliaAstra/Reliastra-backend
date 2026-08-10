package database

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// Pool wraps *pgxpool.Pool with helper methods and metric hooks.
type Pool struct {
	*pgxpool.Pool
}

// Connect opens a PostgreSQL pool and verifies connectivity.
func Connect(ctx context.Context, cfg config.DatabaseConfig) (*Pool, error) {
	poolCfg, err := pgxpool.ParseConfig(cfg.URL)
	if err != nil {
		return nil, fmt.Errorf("database: invalid URL: %w", err)
	}
	poolCfg.MaxConns = int32(cfg.MaxConns)
	poolCfg.MinConns = int32(cfg.MinConns)
	poolCfg.MaxConnLifetime = cfg.MaxConnLifetime
	poolCfg.MaxConnIdleTime = cfg.MaxConnIdleTime
	poolCfg.ConnConfig.ConnectTimeout = cfg.ConnectTimeout
	switch cfg.QueryMode {
	case "simple":
		poolCfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeSimpleProtocol
	case "exec":
		poolCfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeExec
		poolCfg.ConnConfig.StatementCacheCapacity = 0
		poolCfg.ConnConfig.DescriptionCacheCapacity = 0
	case "describe_exec":
		poolCfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeDescribeExec
		poolCfg.ConnConfig.StatementCacheCapacity = 0
		poolCfg.ConnConfig.DescriptionCacheCapacity = 0
	case "cache":
		// pgx default (extended protocol with prepared statement cache).
	default:
		return nil, fmt.Errorf("database: unknown RELI_DATABASE_QUERY_MODE %q", cfg.QueryMode)
	}

	ctx, cancel := context.WithTimeout(ctx, cfg.ConnectTimeout)
	defer cancel()

	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("database: create pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("database: ping: %w", err)
	}
	// Export pool stats periodically for observability.
	go func() {
		t := time.NewTicker(15 * time.Second)
		defer t.Stop()
		for range t.C {
			st := pool.Stat()
			metrics.DBPoolConnections.Set(float64(st.TotalConns()))
		}
	}()
	return &Pool{pool}, nil
}
