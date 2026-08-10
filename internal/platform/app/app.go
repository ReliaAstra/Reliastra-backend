// Package app wires configuration, infrastructure and domain services for
// every runtime process. It is the composition root: no domain package
// depends on it.
package app

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/audit"
	"github.com/ReliaAstra/reliastra-backend/internal/auth"
	"github.com/ReliaAstra/reliastra-backend/internal/billing"
	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/correlation"
	"github.com/ReliaAstra/reliastra-backend/internal/dependencies"
	"github.com/ReliaAstra/reliastra-backend/internal/evidence"
	"github.com/ReliaAstra/reliastra-backend/internal/health"
	"github.com/ReliaAstra/reliastra-backend/internal/incidents"
	"github.com/ReliaAstra/reliastra-backend/internal/monitors"
	"github.com/ReliaAstra/reliastra-backend/internal/notifications"
	"github.com/ReliaAstra/reliastra-backend/internal/organizations"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/database"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/encryption"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/objectstore"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/ratelimit"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/redis"
	"github.com/ReliaAstra/reliastra-backend/internal/projects"
	"github.com/ReliaAstra/reliastra-backend/internal/publictracking"
	"github.com/ReliaAstra/reliastra-backend/internal/regions"
	"github.com/ReliaAstra/reliastra-backend/internal/services"
	"github.com/ReliaAstra/reliastra-backend/pkg/clock"
	"github.com/ReliaAstra/reliastra-backend/pkg/logging"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
	"github.com/ReliaAstra/reliastra-backend/pkg/tracing"
)

// Container is the assembled dependency graph.
type Container struct {
	Cfg          *config.Config
	Logger       *slog.Logger
	Clock        clock.Clock
	Tracer       tracing.Tracer
	Pool         *pgxpool.Pool
	Redis        *redis.Client
	Objects      objectstore.Store
	Encrypter    *encryption.Encrypter
	Outbox       *outbox.Store
	Limiter      ratelimit.Limiter
	Checker      *health.Checker

	Auth        *auth.Service
	Orgs        *organizations.Service
	Projects    *projects.Store
	Services    *services.Store
	Deps        *dependencies.Store
	Regions     *regions.Store
	Monitors    *monitors.Service
	MonitorStore *monitors.Store
	Registry    *monitors.Registry
	Jobs        *checks.JobStore
	Results     *checks.ResultStore
	Observations *checks.ObservationStore
	Incidents   *incidents.Store
	Detector    *incidents.Detector
	Correlator  *correlation.RuleBasedCorrelator
	Evidence    *evidence.Service
	EvidenceStore *evidence.Store
	Channels    *notifications.Store
	Vendors     *publictracking.Store
	Audit       *audit.Store
	Counter     *billing.DBCounter
}

// LoadConfig loads and validates configuration.
func LoadConfig(service string) (*config.Config, error) {
	cfg, err := config.Load()
	if err != nil {
		return nil, err
	}
	cfg.Service = service
	return cfg, nil
}

// New assembles the container for a service. It connects to PostgreSQL (and
// Redis/object storage as configured) and verifies connectivity.
func New(ctx context.Context, cfg *config.Config) (*Container, error) {
	logger := logging.New(os.Stdout, cfg.LogLevel, cfg.Service)
	tracer := &tracing.Noop{Logger: logger}
	tracing.Global = tracer

	pool, err := database.Connect(ctx, cfg.Database)
	if err != nil {
		return nil, err
	}
	rdb, err := redis.Connect(ctx, cfg.Redis)
	if err != nil {
		pool.Close()
		return nil, err
	}

	// Object storage.
	var objects objectstore.Store
	switch cfg.ObjectStore.Backend {
	case "s3":
		s3store, err := objectstore.NewS3(cfg.ObjectStore.Endpoint, cfg.ObjectStore.Bucket,
			cfg.ObjectStore.Region, cfg.ObjectStore.AccessKey, cfg.ObjectStore.SecretKey,
			cfg.ObjectStore.UseSSL, cfg.ObjectStore.Prefix)
		if err != nil {
			pool.Close()
			return nil, err
		}
		objects = s3store
	case "filesystem":
		fsstore, err := objectstore.NewFilesystem(cfg.ObjectStore.FilesystemRoot, cfg.ObjectStore.Prefix)
		if err != nil {
			pool.Close()
			return nil, err
		}
		objects = fsstore
	}

	// Encryption.
	masterKey := cfg.Encryption.MasterKey
	if masterKey == "" {
		// Development default: generate a random ephemeral key. Production
		// requires RELI_ENCRYPTION_MASTER_KEY (validated in config).
		if cfg.Env == "production" {
			pool.Close()
			return nil, fmt.Errorf("app: RELI_ENCRYPTION_MASTER_KEY is required in production")
		}
		key := make([]byte, 32)
		if _, err := rand.Read(key); err != nil {
			pool.Close()
			return nil, err
		}
		masterKey = hex.EncodeToString(key)
	}
	enc, err := encryption.New(masterKey, cfg.Encryption.KeyVersion)
	if err != nil {
		pool.Close()
		return nil, err
	}

	c := &Container{
		Cfg: cfg, Logger: logger, Clock: clock.System(), Tracer: tracer,
		Pool: pool.Pool, Redis: rdb, Objects: objects, Encrypter: enc,
		Outbox: outbox.New(pool.Pool), Checker: health.New(),
	}

	// Infrastructure-backed services.
	if rdb != nil && cfg.RateLimit.RedisEnabled {
		c.Limiter = ratelimit.New(rdb.Client)
	} else {
		c.Limiter = ratelimit.New(nil)
	}

	// Domain stores.
	c.Audit = audit.NewStore(pool.Pool)
	c.Orgs = organizations.NewService(organizations.NewStore(pool.Pool))
	c.Projects = projects.NewStore(pool.Pool)
	c.Services = services.NewStore(pool.Pool)
	c.Deps = dependencies.NewStore(pool.Pool)
	c.Regions = regions.NewStore(pool.Pool)
	c.Counter = billing.NewDBCounter(pool.Pool)
	entitlements := billing.NewEntitlements(cfg.Plans, c.Counter)
	billingProvider := billing.NewStaticProvider(organizations.NewStore(pool.Pool))

	c.MonitorStore = monitors.NewStore(pool.Pool, enc)
	c.Registry = monitors.NewRegistry(monitors.NewHTTPExecutor())
	c.Monitors = monitors.NewService(c.MonitorStore, c.Registry, entitlements, billingProvider,
		monitors.WorkerConfig{
			MaxResponseBytes: cfg.Worker.MaxResponseBytes,
			MaxRedirects:     cfg.Worker.MaxRedirects,
		})

	userStore := auth.NewUserStore(pool.Pool)
	sessStore := auth.NewSessionStore(pool.Pool)
	keyStore := auth.NewAPIKeyStore(pool.Pool)
	c.Auth = auth.NewService(userStore, sessStore, keyStore,
		organizations.NewStore(pool.Pool), cfg.Auth)

	c.Jobs = checks.NewJobStore(pool.Pool)
	c.Results = checks.NewResultStore(pool.Pool)
	c.Observations = checks.NewObservationStore(pool.Pool)

	c.Incidents = incidents.NewStore(pool.Pool)
	c.Correlator = correlation.NewRuleBased(correlation.DataProviders{
		Pool: pool.Pool, Observations: c.Observations, Dependencies: c.Deps,
		Incidents: c.Incidents,
	})
	c.Detector = incidents.NewDetector(pool.Pool, c.Incidents, c.Observations, c.Outbox,
		c.Correlator, cfg.Incident)

	c.EvidenceStore = evidence.NewStore(pool.Pool)
	c.Evidence = evidence.NewService(c.EvidenceStore,
		evidence.NewGatherer(pool.Pool, c.Observations), c.Incidents, c.Observations,
		objects, c.Outbox, cfg.Evidence)

	c.Channels = notifications.NewStore(pool.Pool, enc)
	c.Vendors = publictracking.NewStore(pool.Pool)

	// Readiness checks.
	c.Checker.Register("postgresql", func(ctx context.Context) error {
		return pool.Ping(ctx)
	})
	if rdb != nil {
		c.Checker.Register("redis", func(ctx context.Context) error {
			return rdb.Ping(ctx).Err()
		})
	}
	c.Checker.Register("object_store", func(ctx context.Context) error {
		_, err := objects.Stat(ctx, ".healthcheck")
		if err == objectstore.ErrNotFound {
			return nil // reachable, object absent is fine
		}
		return err
	})

	return c, nil
}

// Close releases infrastructure connections.
func (c *Container) Close() {
	if c.Redis != nil {
		_ = c.Redis.Close()
	}
	c.Pool.Close()
}

var _ = metrics.Registry
