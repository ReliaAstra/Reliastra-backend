// Package integration contains end-to-end tests that exercise the real API,
// scheduler, worker and notifier against a real PostgreSQL (PGlite wire
// server or any PostgreSQL with RELI_TEST_DATABASE_URL).
//
// The test drives the complete Phase 1 flow:
//
//	register -> org -> project -> service -> dependency -> link -> monitor
//	-> scheduler creates jobs -> worker executes checks -> observations
//	-> incident candidate/confirmed -> dependency recovers -> incident
//	resolved -> correlation persists -> evidence generated -> verification.
package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math/rand"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/api"
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
	"github.com/ReliaAstra/reliastra-backend/internal/projects"
	"github.com/ReliaAstra/reliastra-backend/internal/publictracking"
	"github.com/ReliaAstra/reliastra-backend/internal/regions"
	"github.com/ReliaAstra/reliastra-backend/internal/services"
	"github.com/ReliaAstra/reliastra-backend/pkg/clock"
	"github.com/ReliaAstra/reliastra-backend/pkg/logging"
)

func testDBURL(t *testing.T) string {
	u := os.Getenv("RELI_TEST_DATABASE_URL")
	if u == "" {
		u = "postgres://postgres@127.0.0.1:5433/postgres?sslmode=disable"
	}
	return u
}

func connectPool(t *testing.T, ctx context.Context) *pgxpool.Pool {
	t.Helper()
	cfg, err := pgxpool.ParseConfig(testDBURL(t))
	if err != nil {
		t.Fatalf("parse dsn: %v", err)
	}
	cfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeExec
	cfg.ConnConfig.StatementCacheCapacity = 0
	cfg.ConnConfig.DescriptionCacheCapacity = 0
	cfg.MaxConns = 1
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	return pool
}

func cleanDB(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	rows, err := pool.Query(ctx, `SELECT tablename FROM pg_tables WHERE schemaname='public'`)
	if err != nil {
		t.Fatalf("list tables: %v", err)
	}
	var tables []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			t.Fatalf("scan: %v", err)
		}
		tables = append(tables, name)
	}
	rows.Close()
	for _, name := range tables {
		if _, err := pool.Exec(ctx, "DROP TABLE IF EXISTS "+name+" CASCADE"); err != nil {
			t.Fatalf("drop %s: %v", name, err)
		}
	}
}

// flakyServer returns a local HTTP server that fails with 503 for the first
// failRequests requests, then serves 200 with the expected body.
func flakyServer(t *testing.T, failRequests int32, body string) (*httptest.Server, *atomic.Int32) {
	t.Helper()
	var remaining atomic.Int32
	remaining.Store(failRequests)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if remaining.Load() > 0 {
			remaining.Add(-1)
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte("degraded"))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv, &remaining
}

// testComponents assembles the domain layer with a test executor that may
// dial localhost (the production SSRF guard is bypassed only here).
func testComponents(t *testing.T, ctx context.Context, pool *pgxpool.Pool, targetAddr string) (*components, *config.Config) {
	t.Helper()
	enc, err := encryption.New(strings.Repeat("ab", 32), 1) // 32 bytes hex
	if err != nil {
		t.Fatalf("encryption: %v", err)
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{
		Env: "test", Service: "test", LogLevel: "info",
		Database: config.DatabaseConfig{MaxConns: 1, MinConns: 1, QueryMode: "exec"},
		Auth: config.AuthConfig{
			SessionTTL: time.Hour, MinPasswordLength: 8, MaxPasswordLength: 128,
			Argon2Memory: 64 * 1024, Argon2Iterations: 1, Argon2Parallelism: 1, Argon2SaltLength: 16,
			RegisterEnabled: true,
		},
		Scheduler: config.SchedulerConfig{
			PollInterval: 100 * time.Millisecond, BatchSize: 500, Lookahead: time.Hour,
			JitterMaxPct: 0, MissedJobWindow: time.Hour, LeaseDuration: 2 * time.Minute,
			MaxRequeueAttempts: 5, MaxBackoff: time.Minute,
		},
		Worker: config.WorkerConfig{
			Concurrency: 4, JobPollInterval: 50 * time.Millisecond, JobPollBatch: 10,
			MaxResponseBytes: 1 << 20, MaxRedirects: 5, ExecutionTimeout: 5 * time.Second,
			GracefulShutdown: 5 * time.Second, OrgFairnessMaxConcurrent: 4, LeaseDuration: 2 * time.Minute,
		},
		Notifier: config.NotifierConfig{
			PollInterval: 50 * time.Millisecond, BatchSize: 100, MaxDeliveryAttempts: 3,
			BaseBackoff: time.Second, MaxBackoff: 10 * time.Second, DeadLetterAfter: time.Hour,
		},
		Incident: config.IncidentRulesConfig{
			ConsecutiveToCandidate: 2, ConsecutiveToConfirm: 3,
			FailureRateWindow: 5, FailureRateToCandidate: 0.5, FailureRateToConfirm: 0.7,
			RegionsToConfirm: 2, HealthyToResolve: 2, Lookback: time.Hour, MaxObservations: 100,
		},
		Evidence: config.EvidenceConfig{
			Enabled: true, StoragePrefix: "evidence", PDFEnabled: true,
			MethodologyVersion: "v1", CorrelationVersion: "v1", ScoringConfigVersion: "v1",
			MaxObservationFetch: 1000,
		},
		Plans: config.PlanConfig{DefaultPlan: "professional", Plans: map[string]config.PlanLimits{
			"professional": {MaxMonitors: 100, MinIntervalSeconds: 1, MaxProjects: 10,
				MaxMembers: 50, MaxEvidencePerDay: 100, APIRequestsPerMinute: 3000,
				CheckRetentionDays: 180, MaxDependencies: 500, MaxServices: 200,
				MaxRegions: 10, MaxAPIKeys: 50},
		}},
	}
	_ = cfg
	// The real cfg used by services is built inline below (components hold
	// their own references).

	orgStore := organizations.NewStore(pool)
	orgSvc := organizations.NewService(orgStore)
	projectStore := projects.NewStore(pool)
	serviceStore := services.NewStore(pool)
	depStore := dependencies.NewStore(pool)
	regionStore := regions.NewStore(pool)

	registry := monitors.NewRegistry(monitors.NewHTTPExecutorForTest(
		func(ctx context.Context, network, addr string) (net.Conn, error) {
			var d net.Dialer
			return d.DialContext(ctx, network, targetAddr)
		}))
	monitorStore := monitors.NewStore(pool, enc)
	counter := billing.NewDBCounter(pool)
	ent := billing.NewEntitlements(config.PlanConfig{
		DefaultPlan: "professional",
		Plans: map[string]config.PlanLimits{
			"professional": {MaxMonitors: 100, MinIntervalSeconds: 1, MaxProjects: 10,
				MaxMembers: 50, MaxEvidencePerDay: 100, APIRequestsPerMinute: 3000,
				CheckRetentionDays: 180, MaxDependencies: 500, MaxServices: 200,
				MaxRegions: 10, MaxAPIKeys: 50},
		},
	}, counter)
	monitorSvc := monitors.NewService(monitorStore, registry, ent, billing.NewStaticProvider(orgStore),
		monitors.WorkerConfig{MaxResponseBytes: 1 << 20, MaxRedirects: 5})

	userStore := auth.NewUserStore(pool)
	sessStore := auth.NewSessionStore(pool)
	keyStore := auth.NewAPIKeyStore(pool)
	authSvc := auth.NewService(userStore, sessStore, keyStore, orgStore, config.AuthConfig{
		SessionTTL: time.Hour, MinPasswordLength: 8, MaxPasswordLength: 128,
		Argon2Memory: 64 * 1024, Argon2Iterations: 1, Argon2Parallelism: 1, Argon2SaltLength: 16,
	})

	jobStore := checks.NewJobStore(pool)
	resultStore := checks.NewResultStore(pool)
	obsStore := checks.NewObservationStore(pool)
	incStore := incidents.NewStore(pool)
	outboxStore := outbox.New(pool)
	corr := correlation.NewRuleBased(correlation.DataProviders{
		Pool: pool, Observations: obsStore, Dependencies: depStore, Incidents: incStore,
	})
	detector := incidents.NewDetector(pool, incStore, obsStore, outboxStore, corr, config.IncidentRulesConfig{
		ConsecutiveToCandidate: 2, ConsecutiveToConfirm: 3,
		FailureRateWindow: 5, FailureRateToCandidate: 0.5, FailureRateToConfirm: 0.7,
		RegionsToConfirm: 2, HealthyToResolve: 2, Lookback: time.Hour, MaxObservations: 100,
	})
	evStore := evidence.NewStore(pool)
	objects, err := objectstore.NewFilesystem(t.TempDir(), "")
	if err != nil {
		t.Fatalf("object store: %v", err)
	}
	evSvc := evidence.NewService(evStore, evidence.NewGatherer(pool, obsStore), incStore, obsStore,
		objects, outboxStore, config.EvidenceConfig{
			Enabled: true, StoragePrefix: "evidence", PDFEnabled: true,
			MethodologyVersion: "v1", CorrelationVersion: "v1", ScoringConfigVersion: "v1",
			MaxObservationFetch: 1000,
		})
	channelStore := notifications.NewStore(pool, enc)
	vendorStore := publictracking.NewStore(pool)

	retry := checks.NewRetryPolicy(100*time.Millisecond, 5*time.Second, 5, rand.New(rand.NewSource(1)))
	worker := checks.NewWorker("test-worker", "", "test", 4, jobStore, resultStore, obsStore,
		monitorStore, monitorSvc, registry, outboxStore, detector, vendorStore,
		retry, config.WorkerConfig{
			Concurrency: 4, JobPollInterval: 50 * time.Millisecond, JobPollBatch: 10,
			MaxResponseBytes: 1 << 20, MaxRedirects: 5, ExecutionTimeout: 5 * time.Second,
			GracefulShutdown: 5 * time.Second, OrgFairnessMaxConcurrent: 4, LeaseDuration: 2 * time.Minute,
		}, clock.System(), logger)

	scheduler := checks.NewScheduler(monitorStore, jobStore, config.SchedulerConfig{
		PollInterval: 100 * time.Millisecond, BatchSize: 500, Lookahead: time.Hour,
		JitterMaxPct: 0, MissedJobWindow: time.Hour, LeaseDuration: 2 * time.Minute,
		MaxRequeueAttempts: 5, MaxBackoff: time.Minute,
	}, clock.System(), logger)

	return &components{
		pool: pool, logger: logger,
		auth: authSvc, orgs: orgSvc, projects: projectStore, services: serviceStore,
		deps: depStore, regions: regionStore, monitors: monitorSvc, monitorStore: monitorStore,
		jobs: jobStore, results: resultStore, observations: obsStore,
		incidents: incStore, detector: detector, correlator: corr,
		evidence: evSvc, evStore: evStore, channels: channelStore, vendors: vendorStore,
		outbox: outboxStore, objects: objects,
		scheduler: scheduler, worker: worker, checker: health.New(),
		incidentRules: config.IncidentRulesConfig{
			ConsecutiveToCandidate: 2, ConsecutiveToConfirm: 3,
			FailureRateWindow: 5, FailureRateToCandidate: 0.5, FailureRateToConfirm: 0.7,
			RegionsToConfirm: 2, HealthyToResolve: 2, Lookback: time.Hour, MaxObservations: 100,
		},
		workerCfg: config.WorkerConfig{
			Concurrency: 4, JobPollInterval: 50 * time.Millisecond, JobPollBatch: 10,
			MaxResponseBytes: 1 << 20, MaxRedirects: 5, ExecutionTimeout: 5 * time.Second,
			GracefulShutdown: 5 * time.Second, OrgFairnessMaxConcurrent: 4, LeaseDuration: 2 * time.Minute,
		},
		notifierCfg: config.NotifierConfig{
			PollInterval: 50 * time.Millisecond, BatchSize: 100, MaxDeliveryAttempts: 3,
			BaseBackoff: time.Second, MaxBackoff: 10 * time.Second, DeadLetterAfter: time.Hour,
		},
		evidenceCfg: config.EvidenceConfig{
			Enabled: true, StoragePrefix: "evidence", PDFEnabled: true,
			MethodologyVersion: "v1", CorrelationVersion: "v1", ScoringConfigVersion: "v1",
			MaxObservationFetch: 1000,
		},
		rateCfg: config.RateLimitConfig{Enabled: false},
		httpCfg: config.HTTPConfig{TrustedProxyHeaders: false},
		corsCfg: config.CORSConfig{},
	}, cfg
}

type components struct {
	pool    *pgxpool.Pool
	logger  *slog.Logger
	auth    *auth.Service
	orgs    *organizations.Service
	projects *projects.Store
	services *services.Store
	deps    *dependencies.Store
	regions *regions.Store
	monitors *monitors.Service
	monitorStore *monitors.Store
	jobs    *checks.JobStore
	results *checks.ResultStore
	observations *checks.ObservationStore
	incidents *incidents.Store
	detector *incidents.Detector
	correlator *correlation.RuleBasedCorrelator
	evidence *evidence.Service
	evStore *evidence.Store
	channels *notifications.Store
	vendors *publictracking.Store
	outbox *outbox.Store
	objects objectstore.Store
	scheduler *checks.Scheduler
	worker *checks.Worker
	checker *health.Checker
	incidentRules config.IncidentRulesConfig
	workerCfg config.WorkerConfig
	notifierCfg config.NotifierConfig
	evidenceCfg config.EvidenceConfig
	rateCfg config.RateLimitConfig
	httpCfg config.HTTPConfig
	corsCfg config.CORSConfig
}

// startAPI builds and starts the real HTTP API in-process.
func startAPI(t *testing.T, c *components) *httptest.Server {
	t.Helper()
	handlers := api.NewHandlers(api.Dependencies{
		Cfg: &config.Config{
			HTTP: config.HTTPConfig{MaxBodyBytes: 1 << 20, TrustedProxyHeaders: false,
				HealthLivePath: "/health/live", HealthReadyPath: "/health/ready", MetricsPath: "/metrics"},
			RateLimit: config.RateLimitConfig{Enabled: false},
			CORS:      config.CORSConfig{},
		},
		Logger:    c.logger,
		Pool:      c.pool,
		Auth:      c.auth,
		Orgs:      c.orgs,
		Projects:  c.projects,
		Services:  c.services,
		Deps:      c.deps,
		Monitors:  c.monitors,
		Regions:   c.regions,
		Jobs:      c.jobs,
		Results:   c.results,
		Incidents: c.incidents,
		Evidence:  c.evidence,
		EvStore:   c.evStore,
		Channels:  c.channels,
		Vendors:   c.vendors,
		Audit:     nil,
		Objects:   c.objects,
		Outbox:    c.outbox,
		Limiter:   ratelimit.New(nil),
		Checker:   c.checker,
	})
	srv := httptest.NewServer(handlers.Router())
	t.Cleanup(srv.Close)
	return srv
}

// apiClient is a tiny JSON API client for the test.
type apiClient struct {
	base   string
	token  string
	orgID  string
	client *http.Client
}

func (a *apiClient) do(t *testing.T, method, path string, body any) (int, map[string]any) {
	t.Helper()
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, a.base+path, r)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if a.token != "" {
		req.Header.Set("Authorization", "Bearer "+a.token)
	}
	if a.orgID != "" {
		req.Header.Set("X-Reliasorg", a.orgID)
	}
	resp, err := a.client.Do(req)
	if err != nil {
		t.Fatalf("do %s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	out := map[string]any{}
	if len(data) > 0 {
		_ = json.Unmarshal(data, &out)
	}
	return resp.StatusCode, out
}

func (a *apiClient) data(t *testing.T, method, path string, body any) map[string]any {
	t.Helper()
	code, out := a.do(t, method, path, body)
	if code < 200 || code >= 300 {
		t.Fatalf("%s %s: status %d body=%v", method, path, code, out)
	}
	d, _ := out["data"].(map[string]any)
	return d
}

func str(m map[string]any, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

// TestEndToEndIncidentAndEvidence drives the full Phase 1 flow.
func TestEndToEndIncidentAndEvidence(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	pool := connectPool(t, ctx)
	defer pool.Close()

	migrator := database.NewMigrator(pool)
	if _, err := migrator.Up(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	cleanDB(t, ctx, pool)
	if _, err := migrator.Up(ctx); err != nil {
		t.Fatalf("migrate after clean: %v", err)
	}

	// Local flaky target: fails 6 times, then healthy.
	target, _ := flakyServer(t, 6, `{"status":"ok"}`)
	u, err := url.Parse(target.URL)
	if err != nil {
		t.Fatal(err)
	}
	c, _ := testComponents(t, ctx, pool, u.Host)

	// Seed a region.
	region := &regions.Region{Name: "Test", Slug: "test-region", Country: "US", Provider: "local", Status: "active", Capabilities: []string{"http"}}
	region, err = c.regions.Create(ctx, region)
	if err != nil {
		t.Fatalf("region: %v", err)
	}

	// API wiring.
	srv := startAPI(t, c)
	client := &apiClient{base: srv.URL, client: srv.Client()}

	// 1. Register + login.
	client.data(t, "POST", "/v1/auth/register", map[string]any{
		"email": "e2e@reliastra.dev", "password": "e2e-password-123", "name": "E2E"})
	login := client.data(t, "POST", "/v1/auth/login", map[string]any{
		"email": "e2e@reliastra.dev", "password": "e2e-password-123"})
	client.token = str(login, "token")
	if client.token == "" {
		t.Fatal("no token from login")
	}

	// 2. Organization.
	org := client.data(t, "POST", "/v1/organizations", map[string]any{"name": "E2E Org", "slug": "e2e-org"})
	orgObj, _ := org["organization"].(map[string]any)
	client.orgID = str(orgObj, "id")
	if client.orgID == "" {
		t.Fatalf("no org id: %v", org)
	}

	// 3. Project.
	proj := client.data(t, "POST", "/v1/projects", map[string]any{"name": "E2E", "slug": "e2e", "description": ""})
	projObj, _ := proj["project"].(map[string]any)
	projectID := str(projObj, "id")

	// 4. Service.
	svc := client.data(t, "POST", "/v1/services", map[string]any{
		"project_id": projectID, "name": "Checkout API", "identifier": "checkout-api"})
	svcObj, _ := svc["service"].(map[string]any)
	serviceID := str(svcObj, "id")

	// 5. Dependency.
	dep := client.data(t, "POST", "/v1/dependencies", map[string]any{
		"project_id": projectID, "name": "Stripe", "provider": "stripe", "type": "payment"})
	depObj, _ := dep["dependency"].(map[string]any)
	depID := str(depObj, "id")

	// 6. Link (critical).
	link := client.data(t, "POST", "/v1/services/"+serviceID+"/dependencies", map[string]any{
		"dependency_id": depID, "criticality": "critical"})
	if str(link["service_dependency"].(map[string]any), "criticality") != "critical" {
		t.Fatal("link criticality mismatch")
	}

	// 7. Monitor targeting the local service URL.
	cfgBody := map[string]any{
		"url": target.URL, "method": "GET", "expected_status_codes": []int{200},
		"redirect_policy": "follow",
	}
	mon := client.data(t, "POST", "/v1/monitors", map[string]any{
		"project_id": projectID, "service_id": serviceID, "name": "E2E health",
		"type": "http", "interval_seconds": 10, "timeout_seconds": 5,
		"region_ids": []string{region.ID}, "configuration": cfgBody})
	monObj, _ := mon["monitor"].(map[string]any)
	if monObj == nil {
		t.Fatalf("monitor creation failed: %v", mon)
	}

	// 8. Drive scheduler + worker until an incident appears.
	waitFor(t, 60*time.Second, func() bool {
		if err := c.scheduler.Tick(ctx); err != nil {
			t.Logf("scheduler tick: %v", err)
		}
		if _, err := c.worker.PollOnce(ctx); err != nil {
			t.Logf("worker poll: %v", err)
		}
		n, _ := c.incidents.CountOpen(ctx, client.orgID)
		return n > 0
	}, "incident created")

	// 9. Incident visible via API.
	incData := client.data(t, "GET", "/v1/incidents", nil)
	list, _ := incData["incidents"].([]any)
	if len(list) == 0 {
		t.Fatal("no incidents via API")
	}
	first, _ := list[0].(map[string]any)
	incidentID := str(first, "id")
	number := str(first, "number")
	t.Logf("incident %s created (status=%v)", number, first["status"])

	// 10. Target recovers -> checks succeed -> incident resolves.
	waitFor(t, 90*time.Second, func() bool {
		if err := c.scheduler.Tick(ctx); err != nil {
			t.Logf("scheduler tick: %v", err)
		}
		if _, err := c.worker.PollOnce(ctx); err != nil {
			t.Logf("worker poll: %v", err)
		}
		inc, err := c.incidents.ByID(ctx, client.orgID, incidentID)
		if err != nil {
			return false
		}
		return inc.Status == incidents.StatusResolved
	}, "incident resolved")

	// 11. Correlation persisted.
	corrCount := 0
	waitFor(t, 30*time.Second, func() bool {
		if err := c.pool.QueryRow(ctx,
			`SELECT count(*) FROM incident_correlations WHERE incident_id=$1`, incidentID).Scan(&corrCount); err != nil {
			return false
		}
		return corrCount > 0
	}, "correlation persisted")

	// 12. Notifier drains the outbox -> evidence generated.
	notifier := notifications.NewConsumer(c.outbox, c.channels, c.evidence,
		[]notifications.Provider{
			notifications.NewEmailProvider(config.SMTPConfig{}),
			notifications.NewSlackProvider(config.SlackConfig{}),
		}, config.NotifierConfig{
			PollInterval: 50 * time.Millisecond, BatchSize: 100, MaxDeliveryAttempts: 3,
			BaseBackoff: time.Second, MaxBackoff: 10 * time.Second, DeadLetterAfter: time.Hour,
		}, c.logger)
	waitFor(t, 90*time.Second, func() bool {
		_ = notifier.ProcessOnce(ctx)
		recs, err := c.evStore.ListForIncident(ctx, client.orgID, incidentID)
		if err != nil {
			return false
		}
		for _, r := range recs {
			if r.Status == evidence.StatusFinalized {
				return true
			}
		}
		return false
	}, "evidence finalized")

	// 13. Evidence via API + verification.
	evData := client.data(t, "GET", "/v1/incidents/"+incidentID+"/evidence", nil)
	evList, _ := evData["evidence"].([]any)
	if len(evList) == 0 {
		t.Fatal("no evidence records via API")
	}
	ev0, _ := evList[0].(map[string]any)
	evidenceID := str(ev0, "id")
	verify := client.data(t, "GET", "/v1/evidence/"+evidenceID+"/verify", nil)
	vObj, _ := verify["verification"].(map[string]any)
	if vObj == nil || vObj["valid"] != true {
		t.Fatalf("evidence verification failed: %v", verify)
	}
	t.Logf("evidence %s verified: hash=%v", evidenceID, vObj["hash"])

	// 14. Download JSON + PDF artifacts (raw bytes, not the JSON envelope).
	for _, format := range []string{"json", "pdf"} {
		req, _ := http.NewRequest("GET", srv.URL+"/v1/evidence/"+evidenceID+"/download?format="+format, nil)
		req.Header.Set("Authorization", "Bearer "+client.token)
		req.Header.Set("X-Reliasorg", client.orgID)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatalf("download %s: %v", format, err)
		}
		raw, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		if resp.StatusCode != 200 {
			t.Fatalf("download %s: status %d body=%s", format, resp.StatusCode, string(raw))
		}
		if len(raw) == 0 {
			t.Fatalf("download %s: empty", format)
		}
		if format == "pdf" && raw[0] != '%' { // PDF magic: %PDF
			t.Fatalf("download %s: not a PDF (first bytes %q)", format, raw[:min(5, len(raw))])
		}
	}
	t.Log("downloads ok")

	// 15. Public vendor endpoints work.
	vendors := client.doPublic(t, "GET", "/v1/vendors", nil)
	if code, ok := vendors["_code"].(int); !ok || code != 200 {
		t.Fatalf("vendors endpoint: %v", vendors)
	}
}

func (a *apiClient) doPublic(t *testing.T, method, path string, body any) map[string]any {
	t.Helper()
	tok := a.token
	a.token = ""
	defer func() { a.token = tok }()
	code, out := a.do(t, method, path, body)
	out["_code"] = code
	return out
}

// waitFor polls fn until it returns true or the timeout elapses.
func waitFor(t *testing.T, timeout time.Duration, fn func() bool, what string) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if fn() {
			return
		}
		time.Sleep(250 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}

var _ = fmt.Sprintf
var _ = logging.Redact
