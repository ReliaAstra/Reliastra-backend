package checks

import (
	"context"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/ReliaAstra/reliastra-backend/internal/monitors"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/pkg/clock"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
	"github.com/ReliaAstra/reliastra-backend/pkg/logging"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// CheckEvent describes one completed check to the incident pipeline.
type CheckEvent struct {
	MonitorID      string
	TargetType     string // service | dependency | public
	TargetID       string
	OrganizationID string
	ProjectID      string
	RegionID       string
	ObservedAt     time.Time
	Success        bool
	FailureClass   string
	LatencyMS      int
}

// IncidentPipeline processes completed checks (implemented by the incident
// detector in internal/incidents; declared here to avoid a package cycle).
type IncidentPipeline interface {
	OnCheckCompleted(ctx context.Context, ev CheckEvent) error
}

// PublicObservationSink records public vendor observations (implemented in
// internal/publictracking). The write happens on the same transaction as the
// job result so no second pool connection is needed (important for pools with
// MaxConns=1, e.g. embedded/edge deployments) and a crash cannot lose the
// observation.
type PublicObservationSink interface {
	RecordPublicObservation(ctx context.Context, tx pgx.Tx, monitorID, regionID, vendorID string, obs *Observation) error
}

// Worker executes check jobs. Workers are horizontally scalable and
// stateless; all state lives in PostgreSQL.
type Worker struct {
	ID        string
	RegionID  string
	Version   string
	Capacity  int

	jobs         *JobStore
	results      *ResultStore
	observations *ObservationStore
	monitors     *monitors.Store
	monitorSvc   *monitors.Service
	registry     *monitors.Registry
	outbox       *outbox.Store
	detector     IncidentPipeline
	publicSink   PublicObservationSink
	retry        *RetryPolicy
	cfg          config.WorkerConfig
	clock        clock.Clock
	logger       *slog.Logger

	sem      chan struct{}
	orgGate  *orgGate
	wg       sync.WaitGroup
	stopping atomic.Bool
	runCtx   context.Context
}

// NewWorker builds a worker.
func NewWorker(id, regionID, version string, capacity int,
	jobs *JobStore, results *ResultStore, observations *ObservationStore,
	monitorStore *monitors.Store, monitorSvc *monitors.Service,
	registry *monitors.Registry, outbox *outbox.Store, detector IncidentPipeline,
	publicSink PublicObservationSink, retry *RetryPolicy, cfg config.WorkerConfig,
	clk clock.Clock, logger *slog.Logger) *Worker {
	return &Worker{
		ID: id, RegionID: regionID, Version: version, Capacity: capacity,
		jobs: jobs, results: results, observations: observations,
		monitors: monitorStore, monitorSvc: monitorSvc, registry: registry,
		outbox: outbox, detector: detector, publicSink: publicSink,
		retry: retry, cfg: cfg, clock: clk, logger: logger,
		sem:     make(chan struct{}, capacity),
		orgGate: newOrgGate(cfg.OrgFairnessMaxConcurrent),
	}
}

// Run starts the worker loop until ctx is cancelled, then drains gracefully.
func (w *Worker) Run(ctx context.Context) error {
	w.runCtx = ctx
	w.logger.Info("worker starting", "worker_id", w.ID, "region", w.RegionID,
		"capacity", w.Capacity, "version", w.Version)
	metrics.WorkerCapacity.Set(float64(w.Capacity))

	hbCtx, hbCancel := context.WithCancel(context.Background())
	defer hbCancel()
	var hbWg sync.WaitGroup
	hbWg.Add(1)
	go func() {
		defer hbWg.Done()
		w.heartbeatLoop(hbCtx)
	}()

	// Stop accepting new work on cancellation.
	<-ctx.Done()
	w.stopping.Store(true)
	w.logger.Info("worker draining")

	// Wait for in-flight jobs (bounded by the graceful shutdown deadline).
	done := make(chan struct{})
	go func() { w.wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(w.cfg.GracefulShutdown):
		w.logger.Warn("worker drain timeout; abandoning in-flight jobs to lease expiry")
	}

	// Release leases we never started executing so they are retried promptly.
	if err := w.releaseUnstartedLeases(context.Background()); err != nil {
		w.logger.Warn("failed to release unstarted leases", "error", err.Error())
	}
	hbCancel()
	hbWg.Wait()
	w.logger.Info("worker stopped")
	return nil
}

// PollOnce performs one lease+execute cycle (also used by tests). The lease
// acquisition uses ctx (the poll timeout); job execution runs under the
// worker's lifetime context so a short poll interval never cancels a
// long-running check. Each check has its own explicit execution timeout.
func (w *Worker) PollOnce(ctx context.Context) (int, error) {
	jobs, err := w.jobs.LeaseDue(ctx, w.ID, w.leaseDuration(), w.cfg.JobPollBatch)
	if err != nil {
		return 0, err
	}
	execCtx := ctx
	if w.runCtx != nil {
		execCtx = w.runCtx
	}
	for i := range jobs {
		job := jobs[i]
		// The semaphore is acquired inside the goroutine with the worker
		// lifetime context: a short poll interval must never block job
		// execution or leak errors. Jobs wait in the bounded queue.
		w.wg.Add(1)
		go func() {
			defer w.wg.Done()
			select {
			case w.sem <- struct{}{}:
			case <-execCtx.Done():
				return
			}
			defer func() { <-w.sem }()
			if err := w.runJob(execCtx, &job); err != nil {
				w.logger.Error("worker: job failed", "job_id", job.ID, "error", err.Error())
			}
		}()
	}
	return len(jobs), nil
}

func (w *Worker) leaseDuration() time.Duration { return w.cfg.LeaseDuration }

// runJob executes one leased job and persists result + observation.
func (w *Worker) runJob(ctx context.Context, job *Job) error {
	metrics.WorkerActiveJobs.Inc()
	defer metrics.WorkerActiveJobs.Dec()

	if err := w.jobs.MarkRunning(ctx, job.ID, w.ID, w.clock.Now().Add(w.leaseDuration())); err != nil {
		return err
	}
	m, err := w.monitors.ByIDAny(ctx, job.MonitorID)
	if err != nil {
		w.finishUnrecoverable(ctx, job, err)
		return err
	}
	// Org fairness: bound concurrent jobs per organization after the lease is
	// taken; leases are long enough that queued jobs stay valid.
	rel, err := w.orgGate.acquire(ctx, m.OrganizationID)
	if err != nil {
		return err
	}
	defer rel()
	spec, err := w.monitorSvc.BuildRuntimeSpec(ctx, m, job.RegionID, job.ScheduledFor, job.Attempt)
	if err != nil {
		w.finishUnrecoverable(ctx, job, err)
		return err
	}
	ex := w.registry.Get(m.Type)
	if ex == nil {
		w.finishUnrecoverable(ctx, job, errUnsupportedType(m.Type))
		return nil
	}

	started := w.clock.Now()
	outcome, err := ex.Execute(ctx, spec)
	completed := w.clock.Now()
	if err != nil {
		w.finishUnrecoverable(ctx, job, err)
		return err
	}

	// Persist result + observation + job status + outbox event atomically.
	tx, err := w.jobs.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	targetType, targetID, projectID := w.targetOf(m)
	res := &CheckResult{
		JobID: job.ID, Attempt: job.Attempt, MonitorID: m.ID, RegionID: job.RegionID,
		StartedAt: started, CompletedAt: completed, Success: outcome.Success,
		StatusCode: outcome.StatusCode, LatencyMS: outcome.LatencyMS,
		DNSMS: outcome.DNSMS, ConnectMS: outcome.ConnectMS, TLSMS: outcome.TLSMS,
		TTFBMS: outcome.TTFBMS, ErrorClass: outcome.ErrorClass, ErrorCode: outcome.ErrorCode,
		ErrorMessage: outcome.ErrorMessage, ResponseSize: outcome.ResponseSize,
		AssertionsPassed: outcome.AssertionsPassed, AssertionsFailed: outcome.AssertionsFailed,
		Metadata: outcome.Metadata,
	}
	if err := w.results.InsertResult(ctx, tx, res); err != nil {
		return err
	}

	obs := w.observationFor(m, targetType, targetID, projectID, job, res)
	if m.Visibility == "public" {
		if w.publicSink != nil {
			if err := w.publicSink.RecordPublicObservation(ctx, tx, m.ID, job.RegionID, m.VendorID, obs); err != nil {
				return err
			}
		}
	} else {
		if err := w.observations.Insert(ctx, tx, obs); err != nil {
			return err
		}
	}

	// Job final state.
	jobStatus := JobFailed
	if outcome.Success {
		jobStatus = JobSucceeded
		metrics.CheckSuccessTotal.WithLabelValues(m.Type, job.RegionID).Inc()
	} else {
		metrics.CheckFailureTotal.WithLabelValues(m.Type, job.RegionID, outcome.ErrorClass).Inc()
	}
	final := true
	if !outcome.Success && ShouldRetry(outcome.ErrorClass, job.Attempt, m.MaxAttempts) {
		jobStatus = JobPending
		final = false
		nextAttempt := job.Attempt + 1
		retryAfter := w.clock.Now().Add(w.retry.Backoff(job.Attempt))
		if err := w.jobs.RequeueTx(ctx, tx, job.ID, nextAttempt, retryAfter); err != nil {
			return err
		}
		metrics.JobsRetriedTotal.Inc()
	} else {
		if err := w.jobs.Complete(ctx, tx, job.ID, jobStatus, completed); err != nil {
			return err
		}
	}
	metrics.JobsCompletedTotal.WithLabelValues(jobStatus).Inc()

	// Outbox: check completed (drives detection in a decoupled manner).
	if targetType != TargetPublic {
		ev := outbox.Event{
			ID:            ids.NewUUID(),
			EventType:     "check.completed",
			AggregateType: targetType,
			AggregateID:   targetID,
			OrganizationID: m.OrganizationID,
			Payload: map[string]any{
				"monitor_id":    m.ID,
				"target_type":   targetType,
				"target_id":     targetID,
				"region_id":     job.RegionID,
				"observed_at":   obs.ObservedAt.Format(time.RFC3339),
				"success":       outcome.Success,
				"failure_class": outcome.ErrorClass,
				"latency_ms":    outcome.LatencyMS,
				"attempt":       job.Attempt,
				"final":         final,
			},
		}
		if err := w.outbox.Write(ctx, tx, ev); err != nil {
			return err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	// Detection runs after commit (idempotent, re-derivable from the DB).
	if targetType != TargetPublic && w.detector != nil {
		cev := CheckEvent{
			MonitorID: m.ID, TargetType: targetType, TargetID: targetID,
			OrganizationID: m.OrganizationID, ProjectID: projectID,
			RegionID: job.RegionID, ObservedAt: obs.ObservedAt,
			Success: outcome.Success, FailureClass: outcome.ErrorClass, LatencyMS: outcome.LatencyMS,
		}
		if err := w.detector.OnCheckCompleted(context.Background(), cev); err != nil {
			w.logger.Error("incident pipeline error", "error", err.Error(), "monitor_id", m.ID)
		}
	}
	return nil
}

func (w *Worker) targetOf(m *monitors.Monitor) (targetType, targetID, projectID string) {
	if m.Visibility == "public" {
		return TargetPublic, m.VendorID, ""
	}
	if m.ServiceID != "" {
		return TargetService, m.ServiceID, m.ProjectID
	}
	return TargetDependency, m.DependencyID, m.ProjectID
}

func (w *Worker) observationFor(m *monitors.Monitor, targetType, targetID, projectID string,
	job *Job, res *CheckResult) *Observation {
	status := "ok"
	if !res.Success {
		status = "down"
	}
	// Degraded: latency over threshold while available is reported by the
	// executor as a failure; availability semantics stay binary here.
	return &Observation{
		TargetType:     targetType,
		TargetID:       targetID,
		MonitorID:      m.ID,
		RegionID:       job.RegionID,
		OrganizationID: m.OrganizationID,
		ObservedAt:     res.CompletedAt,
		Availability:   res.Success,
		LatencyMS:      res.LatencyMS,
		Status:         status,
		FailureClass:   res.ErrorClass,
		Metadata: map[string]any{
			"job_id":     job.ID,
			"attempt":    job.Attempt,
			"status_code": res.StatusCode,
		},
	}
}

// finishUnrecoverable marks a job failed when execution could not even run
// (bad config, missing monitor). Results are not written; the failure is
// logged and observable.
func (w *Worker) finishUnrecoverable(ctx context.Context, job *Job, cause error) {
	if err := w.jobs.CompleteNow(ctx, job.ID, JobFailed); err != nil {
		w.logger.Error("failed to mark job failed", "job_id", job.ID, "error", err.Error())
	}
	metrics.JobsFailedTotal.Inc()
	metrics.JobsCompletedTotal.WithLabelValues(JobFailed).Inc()
	w.logger.Error("job unrecoverable", "job_id", job.ID, "error", cause.Error())
}

// releaseUnstartedLeases returns jobs this worker leased but never started to
// pending so other workers retry them promptly (graceful shutdown).
func (w *Worker) releaseUnstartedLeases(ctx context.Context) error {
	_, err := w.jobs.pool.Exec(ctx, `UPDATE check_jobs
		SET status='pending', lease_until=NULL, worker_id=''
		WHERE worker_id=$1 AND status='leased'`, w.ID)
	return err
}

func errUnsupportedType(t string) error {
	return &unsupportedTypeError{t}
}

type unsupportedTypeError struct{ t string }

func (e *unsupportedTypeError) Error() string { return "unsupported monitor type: " + e.t }

// orgGate bounds concurrent jobs per organization (fairness). orgID ""
// (public monitors) shares one bucket.
type orgGate struct {
	mu    sync.Mutex
	sems  map[string]chan struct{}
	max   int
}

func newOrgGate(max int) *orgGate {
	return &orgGate{sems: map[string]chan struct{}{}, max: max}
}

// acquire blocks until a slot for orgID is free; the returned release func
// must be called exactly once.
func (g *orgGate) acquire(ctx context.Context, orgID string) (func(), error) {
	g.mu.Lock()
	sem, ok := g.sems[orgID]
	if !ok {
		sem = make(chan struct{}, g.max)
		g.sems[orgID] = sem
	}
	g.mu.Unlock()
	select {
	case sem <- struct{}{}:
		return func() { <-sem }, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// heartbeatLoop keeps the worker registry fresh while running.
func (w *Worker) heartbeatLoop(ctx context.Context) {
	t := time.NewTicker(15 * time.Second)
	defer t.Stop()
	w.heartbeat(ctx)
	for {
		select {
		case <-ctx.Done():
			w.heartbeatStopped()
			return
		case <-t.C:
			w.heartbeat(ctx)
		}
	}
}

func (w *Worker) heartbeat(ctx context.Context) {
	status := "running"
	if w.stopping.Load() {
		status = "draining"
	}
	_, err := w.jobs.pool.Exec(ctx, `INSERT INTO workers (id, region_id, version, capacity, status, heartbeat_at)
		VALUES ($1,$2,$3,$4,$5, now())
		ON CONFLICT (id) DO UPDATE SET heartbeat_at=now(), status=EXCLUDED.status, capacity=EXCLUDED.capacity`,
		w.ID, nullableOrgUUID(w.RegionID), w.Version, w.Capacity, status)
	if err != nil {
		w.logger.Warn("worker heartbeat failed", "error", err.Error())
	}
}

func (w *Worker) heartbeatStopped() {
	_, _ = w.jobs.pool.Exec(context.Background(),
		`UPDATE workers SET status='stopped', stopped_at=now() WHERE id=$1`, w.ID)
}

// nullableOrgUUID is a tiny helper to keep imports tidy.
func nullableOrgUUID(s string) any {
	if s == "" {
		return nil
	}
	return s
}

var _ = pgx.TxOptions{}
var _ = logging.Redact
