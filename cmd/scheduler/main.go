// Command scheduler creates durable check jobs for due monitors. It never
// executes checks. Multiple schedulers may run concurrently; job creation is
// idempotent.
package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/app"
)

func main() {
	cfg, err := app.LoadConfig("scheduler")
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

	scheduler := checks.NewScheduler(container.MonitorStore, container.Jobs,
		cfg.Scheduler, container.Clock, container.Logger)

	tick := time.NewTicker(cfg.Scheduler.PollInterval)
	defer tick.Stop()

	container.Logger.Info("scheduler started",
		"poll_interval", cfg.Scheduler.PollInterval.String(),
		"batch_size", cfg.Scheduler.BatchSize)

	for {
		select {
		case <-ctx.Done():
			container.Logger.Info("scheduler stopped")
			return
		case <-tick.C:
			runCtx, cancel := context.WithTimeout(context.Background(), cfg.Scheduler.PollInterval)
			if err := scheduler.Tick(runCtx); err != nil {
				container.Logger.Error("scheduler tick failed", "error", err.Error())
			}
			cancel()
		}
	}
}

func fatal(err error) {
	os.Stderr.WriteString("scheduler: " + err.Error() + "\n")
	os.Exit(1)
}
