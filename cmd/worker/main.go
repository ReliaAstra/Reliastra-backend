// Command worker executes check jobs leased from PostgreSQL. Workers are
// horizontally scalable, stateless and org-fair (bounded concurrency per
// organization).
package main

import (
	"context"
	"math/rand"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/app"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

func main() {
	cfg, err := app.LoadConfig("worker")
	if err != nil {
		fatal(err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	container, err := app.New(ctx, cfg)
	if err != nil {
		fatal(err)
	}
	defer container.Close()

	// Worker identity: region comes from configuration (slug or id); the id
	// is unique per process. version is the build version (see Makefile
	// ldflags).
	regionID := os.Getenv("RELI_WORKER_REGION_ID")
	if regionID != "" {
		resolved, err := resolveRegionID(ctx, container.Pool, regionID)
		if err != nil {
			container.Logger.Warn("could not resolve worker region", "region", regionID, "error", err.Error())
		} else {
			regionID = resolved
		}
	}
	version := os.Getenv("RELI_BUILD_VERSION")
	if version == "" {
		version = "dev"
	}
	workerID := os.Getenv("RELI_WORKER_ID")
	if workerID == "" {
		workerID = "worker-" + ids.NewToken(6)
	}

	retry := checks.NewRetryPolicy(
		cfg.Scheduler.MaxBackoff/8, cfg.Scheduler.MaxBackoff,
		cfg.Scheduler.MaxRequeueAttempts, rand.New(rand.NewSource(time.Now().UnixNano())))

	worker := checks.NewWorker(workerID, regionID, version, cfg.Worker.Concurrency,
		container.Jobs, container.Results, container.Observations,
		container.MonitorStore, container.Monitors, container.Registry,
		container.Outbox, container.Detector, container.Vendors,
		retry, cfg.Worker, container.Clock, container.Logger)

	poll := time.NewTicker(cfg.Worker.JobPollInterval)
	defer poll.Stop()

	// Leasing loop in a goroutine; Run() blocks until ctx cancellation and
	// then drains gracefully.
	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case <-poll.C:
				// The lease query gets a generous timeout (it can be delayed
				// behind other writers); job execution is governed by the
				// worker lifetime context and per-check timeouts, never by
				// this poll context.
				runCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
				if _, err := worker.PollOnce(runCtx); err != nil && err != context.Canceled {
					container.Logger.Error("worker poll failed", "error", err.Error())
				}
				cancel()
			}
		}
	}()

	if err := worker.Run(ctx); err != nil {
		container.Logger.Error("worker failed", "error", err.Error())
		os.Exit(1)
	}
}

// resolveRegionID accepts a region UUID or slug and returns the UUID.
func resolveRegionID(ctx context.Context, pool *pgxpool.Pool, value string) (string, error) {
	var id string
	err := pool.QueryRow(ctx,
		`SELECT id FROM regions WHERE slug=$1 OR id::text=$1`, value).Scan(&id)
	if err != nil {
		return "", err
	}
	return id, nil
}

func fatal(err error) {
	os.Stderr.WriteString("worker: " + err.Error() + "\n")
	os.Exit(1)
}
