// Command api runs the Reliastra HTTP API. The API is stateless: it never
// executes monitoring checks synchronously.
package main

import (
	"context"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/api"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/app"
)

func main() {
	cfg, err := app.LoadConfig("api")
	if err != nil {
		fatal("config", err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	container, err := app.New(ctx, cfg)
	if err != nil {
		fatal("startup", err)
	}
	defer container.Close()

	handlers := api.NewHandlers(api.Dependencies{
		Cfg:        cfg,
		Logger:     container.Logger,
		Pool:       container.Pool,
		Auth:       container.Auth,
		Orgs:       container.Orgs,
		Projects:   container.Projects,
		Services:   container.Services,
		Deps:       container.Deps,
		Monitors:   container.Monitors,
		Regions:    container.Regions,
		Jobs:       container.Jobs,
		Results:    container.Results,
		Incidents:  container.Incidents,
		Evidence:   container.Evidence,
		EvStore:    container.EvidenceStore,
		Channels:   container.Channels,
		Vendors:    container.Vendors,
		Audit:      container.Audit,
		Objects:    container.Objects,
		Outbox:     container.Outbox,
		Limiter:    container.Limiter,
		Checker:    container.Checker,
	})

	srv := &http.Server{
		Addr:              cfg.HTTP.Addr,
		Handler:           handlers.Router(),
		ReadTimeout:       cfg.HTTP.ReadTimeout,
		WriteTimeout:      cfg.HTTP.WriteTimeout,
		IdleTimeout:       cfg.HTTP.IdleTimeout,
		MaxHeaderBytes:    cfg.HTTP.MaxHeaderBytes,
	}

	errCh := make(chan error, 1)
	go func() {
		container.Logger.Info("api listening", "addr", cfg.HTTP.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	select {
	case err := <-errCh:
		fatal("serve", err)
	case <-ctx.Done():
		container.Logger.Info("api shutting down")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.HTTP.ShutdownTimeout)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			container.Logger.Warn("api shutdown error", "error", err.Error())
		}
		container.Logger.Info("api stopped")
	}
}

func fatal(step string, err error) {
	// Fail fast with a clear message; structured logging is initialized by app.New.
	os.Stderr.WriteString("api: " + step + ": " + err.Error() + "\n")
	os.Exit(1)
}

var _ = time.Second
