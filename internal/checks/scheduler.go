package checks

import (
	"context"
	"math/rand"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/monitors"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/clock"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// SchedulerLogger is the minimal logger the scheduler needs.
type SchedulerLogger interface {
	Info(msg string, args ...any)
	Warn(msg string, args ...any)
}

// Scheduler creates durable jobs for due monitors. It never executes checks.
// Multiple scheduler processes may run concurrently; job creation is
// idempotent (unique monitor+region+scheduled_for) and next_run_at advances
// are conditional, so duplicates are impossible.
type Scheduler struct {
	monitors *monitors.Store
	jobs     *JobStore
	cfg      config.SchedulerConfig
	clock    clock.Clock
	rng      *rand.Rand
	logger   SchedulerLogger
}

// NewScheduler builds a scheduler.
func NewScheduler(monitors *monitors.Store, jobs *JobStore, cfg config.SchedulerConfig,
	clk clock.Clock, logger SchedulerLogger) *Scheduler {
	return &Scheduler{
		monitors: monitors,
		jobs:     jobs,
		cfg:      cfg,
		clock:    clk,
		rng:      rand.New(rand.NewSource(time.Now().UnixNano())),
		logger:   logger,
	}
}

// Tick performs one scheduling pass: reclaim expired leases, create jobs for
// due monitors, advance next_run_at.
func (s *Scheduler) Tick(ctx context.Context) error {
	// 1. Reclaim abandoned jobs (worker died).
	requeued, expired, err := s.jobs.ExpireLeases(ctx, s.clock.Now(), s.cfg.MaxRequeueAttempts,
		func(attempt int) time.Duration {
			return s.jitteredBackoff(attempt)
		})
	if err != nil {
		return err
	}
	if requeued > 0 || expired > 0 {
		metrics.JobsRequeuedTotal.Add(float64(requeued))
		metrics.JobsExpiredTotal.Add(float64(expired))
	}

	// 2. Find due monitors.
	due, err := s.monitors.DueMonitors(ctx, s.cfg.Lookahead, s.cfg.BatchSize)
	if err != nil {
		return err
	}
	now := s.clock.Now()
	for _, m := range due {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		if err := s.scheduleMonitor(ctx, &m, now); err != nil {
			s.logger.Warn("scheduler: failed to schedule monitor", "monitor_id", m.ID, "error", err.Error())
			continue
		}
	}
	return nil
}

func (s *Scheduler) scheduleMonitor(ctx context.Context, m *monitors.Monitor, now time.Time) error {
	interval := time.Duration(m.IntervalSeconds) * time.Second

	// Missed-job handling: if the monitor is far behind (e.g. was disabled),
	// drop the backlog instead of creating a burst of jobs.
	if m.NextRunAt.Before(now.Add(-s.cfg.MissedJobWindow)) {
		metrics.JobsRequeuedTotal.Inc()
		return s.monitors.SetNextRun(ctx, m.ID, now)
	}

	regionIDs, err := s.monitors.ListRegionsForMonitor(ctx, m.ID)
	if err != nil {
		return err
	}
	if len(regionIDs) == 0 {
		return nil // no regions assigned; nothing to schedule
	}

	// Jitter spreads simultaneous due monitors to avoid thundering herds.
	jitter := s.jitter(interval)
	scheduledFor := m.NextRunAt.Add(jitter)
	for _, regionID := range regionIDs {
		job := &Job{
			ID:           ids.NewUUID(),
			MonitorID:    m.ID,
			RegionID:     regionID,
			ScheduledFor: scheduledFor,
			Attempt:      1,
		}
		created, err := s.jobs.CreateJob(ctx, job)
		if err != nil {
			return err
		}
		if created {
			metrics.JobsCreatedTotal.WithLabelValues(m.Type).Inc()
		}
	}
	return s.monitors.AdvanceNextRun(ctx, m.ID, m.NextRunAt, interval)
}

// jitter returns a random offset within ±jitterMaxPct of the interval.
func (s *Scheduler) jitter(interval time.Duration) time.Duration {
	max := time.Duration(float64(interval) * s.cfg.JitterMaxPct)
	if max <= 0 {
		return 0
	}
	return time.Duration(s.rng.Int63n(2*int64(max)) - int64(max))
}

// jitteredBackoff reuses the retry policy for lease-expiry requeues.
func (s *Scheduler) jitteredBackoff(attempt int) time.Duration {
	policy := NewRetryPolicy(s.cfg.MaxBackoff/8, s.cfg.MaxBackoff, s.cfg.MaxRequeueAttempts, s.rng)
	return policy.Backoff(attempt)
}
