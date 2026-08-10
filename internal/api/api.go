// Package api assembles the HTTP API: routing, middleware wiring and the
// handler set. Handlers are thin adapters over services; business logic lives
// in the domain packages.
package api

import (
	"context"
	"log/slog"
	"net/http"

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
	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/objectstore"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/ratelimit"
	"github.com/ReliaAstra/reliastra-backend/internal/projects"
	"github.com/ReliaAstra/reliastra-backend/internal/publictracking"
	"github.com/ReliaAstra/reliastra-backend/internal/regions"
	"github.com/ReliaAstra/reliastra-backend/internal/services"
	"github.com/ReliaAstra/reliastra-backend/pkg/logging"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// Dependencies wires everything the API handlers need.
type Dependencies struct {
	Cfg      *config.Config
	Logger   *slog.Logger
	Pool     *pgxpool.Pool
	Auth     *auth.Service
	Orgs     *organizations.Service
	Projects *projects.Store
	Services *services.Store
	Deps     *dependencies.Store
	Monitors *monitors.Service
	Regions  *regions.Store
	Jobs     *checks.JobStore
	Results  *checks.ResultStore
	Incidents *incidents.Store
	Evidence *evidence.Service
	EvStore  *evidence.Store
	Channels *notifications.Store
	Vendors  *publictracking.Store
	Audit    *audit.Store
	Objects  objectstore.Store
	Outbox   *outbox.Store
	Limiter  ratelimit.Limiter
	Checker  *health.Checker
}

// Handlers carries all request handlers.
type Handlers struct {
	deps  Dependencies
	log   *slog.Logger
}

// NewHandlers builds the handler set.
func NewHandlers(deps Dependencies) *Handlers {
	return &Handlers{deps: deps, log: deps.Logger}
}

// Router builds the full HTTP handler with middleware.
func (h *Handlers) Router() http.Handler {
	mux := http.NewServeMux()
	mw := httpapi.MiddlewareDeps{
		Logger:  h.log,
		Auth:    h.deps.Auth,
		Limiter: h.deps.Limiter,
		RateCfg: h.deps.Cfg.RateLimit,
		CORS:    h.deps.Cfg.CORS,
		HTTP:    h.deps.Cfg.HTTP,
	}

	base := func(scope string, inner http.Handler) http.Handler {
		var next http.Handler = inner
		next = httpapi.WithRateLimit(mw, scope)(next)
		next = httpapi.WithBodyLimit(h.deps.Cfg.HTTP.MaxBodyBytes)(next)
		next = httpapi.WithRecovery(h.log)(next)
		next = httpapi.WithLogging(mw)(next)
		next = httpapi.WithRequestID(next)
		return next
	}
	authed := func(inner http.Handler) http.Handler {
		// Order matters: authenticate first, then resolve the org scope.
		return base("api", httpapi.WithAuthn(mw)(httpapi.WithOrgScope(mw)(inner)))
	}
	// authedNoOrg authenticates but does not require/resolve an org scope
	// (used by /v1/me and organization endpoints, which must work for users
	// who do not belong to any organization yet).
	authedNoOrg := func(inner http.Handler) http.Handler {
		return base("api", httpapi.WithAuthn(mw)(inner))
	}
	pub := func(inner http.Handler) http.Handler {
		return base("public", inner)
	}
	authn := func(inner http.Handler) http.Handler {
		return base("auth", inner)
	}

	// Health and metrics are unauthenticated.
	mux.Handle("GET "+h.deps.Cfg.HTTP.HealthLivePath, pub(http.HandlerFunc(h.healthLive)))
	mux.Handle("GET "+h.deps.Cfg.HTTP.HealthReadyPath, pub(http.HandlerFunc(h.healthReady)))
	mux.Handle("GET "+h.deps.Cfg.HTTP.MetricsPath, pub(http.HandlerFunc(h.metrics())))

	// Authentication.
	mux.Handle("POST /v1/auth/register", authn(http.HandlerFunc(h.register)))
	mux.Handle("POST /v1/auth/login", authn(http.HandlerFunc(h.login)))
	mux.Handle("POST /v1/auth/logout", authn(http.HandlerFunc(h.logout)))
	mux.Handle("GET /v1/me", authedNoOrg(http.HandlerFunc(h.me)))

	// Organizations (no org scope required: these bootstrap tenancy).
	mux.Handle("GET /v1/organizations", authedNoOrg(http.HandlerFunc(h.listOrganizations)))
	mux.Handle("POST /v1/organizations", authedNoOrg(http.HandlerFunc(h.createOrganization)))

	// Projects.
	mux.Handle("GET /v1/projects", authed(http.HandlerFunc(h.listProjects)))
	mux.Handle("POST /v1/projects", authed(http.HandlerFunc(h.createProject)))
	mux.Handle("GET /v1/projects/{id}", authed(http.HandlerFunc(h.getProject)))
	mux.Handle("PATCH /v1/projects/{id}", authed(http.HandlerFunc(h.updateProject)))
	mux.Handle("DELETE /v1/projects/{id}", authed(http.HandlerFunc(h.deleteProject)))

	// Services.
	mux.Handle("GET /v1/services", authed(http.HandlerFunc(h.listServices)))
	mux.Handle("POST /v1/services", authed(http.HandlerFunc(h.createService)))
	mux.Handle("GET /v1/services/{id}", authed(http.HandlerFunc(h.getService)))
	mux.Handle("PATCH /v1/services/{id}", authed(http.HandlerFunc(h.updateService)))
	mux.Handle("DELETE /v1/services/{id}", authed(http.HandlerFunc(h.deleteService)))

	// Dependencies + relationships.
	mux.Handle("GET /v1/dependencies", authed(http.HandlerFunc(h.listDependencies)))
	mux.Handle("POST /v1/dependencies", authed(http.HandlerFunc(h.createDependency)))
	mux.Handle("GET /v1/dependencies/{id}", authed(http.HandlerFunc(h.getDependency)))
	mux.Handle("DELETE /v1/dependencies/{id}", authed(http.HandlerFunc(h.deleteDependency)))
	mux.Handle("POST /v1/services/{id}/dependencies", authed(http.HandlerFunc(h.linkDependency)))
	mux.Handle("DELETE /v1/services/{id}/dependencies/{dependencyID}", authed(http.HandlerFunc(h.unlinkDependency)))

	// Monitors.
	mux.Handle("GET /v1/monitors", authed(http.HandlerFunc(h.listMonitors)))
	mux.Handle("POST /v1/monitors", authed(http.HandlerFunc(h.createMonitor)))
	mux.Handle("GET /v1/monitors/{id}", authed(http.HandlerFunc(h.getMonitor)))
	mux.Handle("PATCH /v1/monitors/{id}", authed(http.HandlerFunc(h.updateMonitor)))
	mux.Handle("DELETE /v1/monitors/{id}", authed(http.HandlerFunc(h.deleteMonitor)))
	mux.Handle("GET /v1/monitors/{id}/results", authed(http.HandlerFunc(h.monitorResults)))

	// Regions.
	mux.Handle("GET /v1/regions", authed(http.HandlerFunc(h.listRegions)))

	// Incidents.
	mux.Handle("GET /v1/incidents", authed(http.HandlerFunc(h.listIncidents)))
	mux.Handle("GET /v1/incidents/{id}", authed(http.HandlerFunc(h.getIncident)))
	mux.Handle("POST /v1/incidents/{id}/evidence", authed(http.HandlerFunc(h.generateEvidence)))
	mux.Handle("GET /v1/incidents/{id}/evidence", authed(http.HandlerFunc(h.incidentEvidence)))

	// Evidence.
	mux.Handle("GET /v1/evidence/{id}", authed(http.HandlerFunc(h.getEvidence)))
	mux.Handle("GET /v1/evidence/{id}/verify", authed(http.HandlerFunc(h.verifyEvidence)))
	mux.Handle("GET /v1/evidence/{id}/download", authed(http.HandlerFunc(h.downloadEvidence)))

	// API keys.
	mux.Handle("GET /v1/api-keys", authed(http.HandlerFunc(h.listAPIKeys)))
	mux.Handle("POST /v1/api-keys", authed(http.HandlerFunc(h.createAPIKey)))
	mux.Handle("DELETE /v1/api-keys/{id}", authed(http.HandlerFunc(h.revokeAPIKey)))

	// Notification channels.
	mux.Handle("GET /v1/notification-channels", authed(http.HandlerFunc(h.listChannels)))
	mux.Handle("POST /v1/notification-channels", authed(http.HandlerFunc(h.createChannel)))
	mux.Handle("DELETE /v1/notification-channels/{id}", authed(http.HandlerFunc(h.deleteChannel)))

	// Audit.
	mux.Handle("GET /v1/audit-logs", authed(http.HandlerFunc(h.listAuditLogs)))

	// Public vendor tracking (no auth; strictly public data).
	mux.Handle("GET /v1/vendors", pub(http.HandlerFunc(h.listVendors)))
	mux.Handle("GET /v1/vendors/{slug}", pub(http.HandlerFunc(h.getVendor)))
	mux.Handle("GET /v1/vendors/{slug}/status", pub(http.HandlerFunc(h.vendorStatus)))
	mux.Handle("GET /v1/vendors/{slug}/observations", pub(http.HandlerFunc(h.vendorObservations)))

	return httpapi.WithSecurityHeaders(mux)
}

// metrics serves Prometheus metrics.
func (h *Handlers) metrics() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		registry := metrics.Registry
		httpapi.WriteMetrics(w, r, registry)
	}
}

var _ = correlation.AlgorithmVersion
var _ = billing.NewStaticProvider
var _ = logging.Redact
var _ = context.Background
