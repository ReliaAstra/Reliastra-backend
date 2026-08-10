// Command notifier drains the transactional outbox: it fans domain events out
// to notification channels (email, Slack) and triggers async evidence
// generation. A failed provider never affects domain transactions.
package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/ReliaAstra/reliastra-backend/internal/notifications"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/app"
)

func main() {
	cfg, err := app.LoadConfig("notifier")
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

	providers := []notifications.Provider{
		notifications.NewEmailProvider(cfg.SMTP),
		notifications.NewSlackProvider(cfg.Slack),
	}
	consumer := notifications.NewConsumer(container.Outbox, container.Channels,
		container.Evidence, providers, cfg.Notifier, container.Logger)

	container.Logger.Info("notifier started",
		"poll_interval", cfg.Notifier.PollInterval.String(),
		"max_delivery_attempts", cfg.Notifier.MaxDeliveryAttempts)

	if err := consumer.Run(ctx); err != nil {
		container.Logger.Error("notifier failed", "error", err.Error())
		os.Exit(1)
	}
	container.Logger.Info("notifier stopped")
}

func fatal(err error) {
	os.Stderr.WriteString("notifier: " + err.Error() + "\n")
	os.Exit(1)
}
