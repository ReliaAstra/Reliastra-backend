package incidents

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Detector implements checks.IncidentPipeline with deterministic rules.
//
// Rules (v1, see docs/architecture/correlation-algorithm.md):
//   - Candidate: N consecutive failures OR failure rate >= R over the last W
//     observations.
//   - Confirm: M consecutive failures OR failure rate >= S OR failure observed
//     from >= K regions.
//   - Resolve: H consecutive healthy observations (confirmed/investigating).
//   - False positive: H consecutive healthy observations (candidate).
//
// Detection is idempotent: it re-derives state from durable observations, and
// a unique partial index guarantees a single open incident per target.
type Detector struct {
	pool         *pgxpool.Pool
	incidents    *Store
	observations *checks.ObservationStore
	outbox       *outbox.Store
	correlator   Correlator
	rules        config.IncidentRulesConfig
	now          func() time.Time
}

// NewDetector builds the detector.
func NewDetector(pool *pgxpool.Pool, inc *Store, obs *checks.ObservationStore,
	outbox *outbox.Store, correlator Correlator, rules config.IncidentRulesConfig) *Detector {
	return &Detector{
		pool: pool, incidents: inc, observations: obs, outbox: outbox,
		correlator: correlator, rules: rules, now: time.Now,
	}
}

// targetStats summarizes recent observations for decision making.
type targetStats struct {
	consecutiveFailures  int
	consecutiveHealthy   int
	failureRate          float64
	failingRegions       int
	allRegions           int
	latestObservedAt     time.Time
}

// OnCheckCompleted implements checks.IncidentPipeline.
func (d *Detector) OnCheckCompleted(ctx context.Context, ev checks.CheckEvent) error {
	if ev.TargetType == checks.TargetPublic || ev.TargetID == "" {
		return nil
	}
	from := ev.ObservedAt.Add(-d.rules.Lookback)
	obs, err := d.observations.RecentForTarget(ctx, ev.TargetType, ev.TargetID, from, ev.ObservedAt.Add(time.Minute), d.rules.MaxObservations)
	if err != nil {
		return fmt.Errorf("detector: observations: %w", err)
	}
	// RecentForTarget returns newest first; reverse to chronological.
	obs = reverseObservations(obs)
	stats := computeStats(obs, d.rules)

	serviceID, dependencyID := "", ""
	if ev.TargetType == checks.TargetService {
		serviceID = ev.TargetID
	} else {
		dependencyID = ev.TargetID
	}

	open, err := d.incidents.OpenForTarget(ctx, serviceID, dependencyID)
	if err != nil && !isNotFound(err) {
		return fmt.Errorf("detector: open incident: %w", err)
	}

	lastObs := stats.latestObservedAt
	if lastObs.IsZero() {
		lastObs = ev.ObservedAt
	}

	switch {
	case open == nil:
		// No open incident: open one when the rules say so.
		if !ev.Success && d.isCandidate(stats) {
			confirm := d.isConfirmed(stats)
			return d.createIncident(ctx, ev, stats, confirm, lastObs)
		}
		return nil
	case ev.Success:
		// Recovery path.
		if stats.consecutiveHealthy >= d.rules.HealthyToResolve {
			to := StatusResolved
			if open.Status == StatusCandidate {
				to = StatusFalsePositive
			}
			return d.transition(ctx, open, to,
				fmt.Sprintf("recovered after %d healthy observations", stats.consecutiveHealthy))
		}
		return nil
	default:
		// Still failing: escalate when evidence strengthens.
		if (open.Status == StatusCandidate || open.Status == StatusInvestigating) && d.isConfirmed(stats) {
			return d.transition(ctx, open, StatusConfirmed,
				fmt.Sprintf("failure rate %.0f%% / %d consecutive / %d regions",
					stats.failureRate*100, stats.consecutiveFailures, stats.failingRegions))
		}
		return nil
	}
}

// createIncident inserts a new incident (candidate or immediately confirmed),
// its initial event, and outbox events, then runs correlation when the
// incident targets a service.
func (d *Detector) createIncident(ctx context.Context, ev checks.CheckEvent, stats targetStats, confirm bool, observedAt time.Time) error {
	title, summary := d.describe(ctx, ev, stats)
	status := StatusCandidate
	if confirm {
		status = StatusConfirmed
	}
	severity := SeverityMedium
	if confirm && stats.failingRegions >= d.rules.RegionsToConfirm {
		severity = SeverityHigh
	}

	tx, err := d.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	number, err := d.incidents.NextNumber(ctx, tx, time.Now().UTC().Year())
	if err != nil {
		return err
	}
	inc := &Incident{
		ProjectID: ev.ProjectID, OrganizationID: ev.OrganizationID,
		ServiceID: targetID(ev, checks.TargetService), DependencyID: targetID(ev, checks.TargetDependency),
		Status: status, Severity: severity,
		StartedAt: observedAt.Add(-5 * time.Minute), DetectedAt: time.Now().UTC(),
		Title: title, Summary: summary,
		Number: number,
	}
	created, err := d.incidents.Create(ctx, tx, inc)
	if err != nil {
		if isUniqueViolation(err) {
			// Another worker won the race; nothing to do.
			return nil
		}
		return err
	}
	meta := map[string]any{"target_type": ev.TargetType, "trigger_observation": ev.MonitorID}
	if err := d.insertEvent(ctx, tx, created, "", status, "detected by rules", meta); err != nil {
		return err
	}
	// Outbox events (same transaction as the incident).
	events := []outbox.Event{
		{ID: ids.NewUUID(), EventType: "incident.created", AggregateType: "incident",
			AggregateID: created.ID, OrganizationID: ev.OrganizationID,
			Payload: map[string]any{"incident_id": created.ID, "number": created.Number,
				"status": status, "severity": severity, "title": title}},
		{ID: ids.NewUUID(), EventType: "monitor.failed", AggregateType: ev.TargetType,
			AggregateID: ev.TargetID, OrganizationID: ev.OrganizationID,
			Payload: map[string]any{"monitor_id": ev.MonitorID, "failure_class": ev.FailureClass}},
	}
	if confirm {
		events = append(events, outbox.Event{
			ID: ids.NewUUID(), EventType: "incident.confirmed", AggregateType: "incident",
			AggregateID: created.ID, OrganizationID: ev.OrganizationID,
			Payload: map[string]any{"incident_id": created.ID, "number": created.Number, "title": title},
		})
	}
	for _, e := range events {
		if err := d.outbox.Write(ctx, tx, e); err != nil {
			return err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	// Correlation for service incidents (post-commit; idempotent upserts).
	if ev.TargetType == checks.TargetService && d.correlator != nil {
		inc.Status = status
		if _, err := d.correlator.Run(ctx, inc); err != nil {
			return fmt.Errorf("detector: correlation: %w", err)
		}
	}
	return nil
}

// transition applies an allowed state change with its event + outbox.
func (d *Detector) transition(ctx context.Context, inc *Incident, to, reason string) error {
	tx, err := d.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if err := d.incidents.Transition(ctx, tx, inc, to, reason, "system", "detector", nil); err != nil {
		if _, ok := err.(*ErrInvalidTransition); ok {
			return nil // e.g. already resolved by another worker
		}
		if errors.KindOf(err) == errors.KindConflict {
			return nil // state changed concurrently; next check re-evaluates
		}
		return err
	}
	eventType := "incident." + to
	ev := outbox.Event{
		ID: ids.NewUUID(), EventType: eventType, AggregateType: "incident",
		AggregateID: inc.ID, OrganizationID: inc.OrganizationID,
		Payload: map[string]any{"incident_id": inc.ID, "number": inc.Number, "status": to},
	}
	if to == StatusResolved {
		ev.Payload["title"] = inc.Title
		ev.Payload["resolved_at"] = inc.ResolvedAt.Format(time.RFC3339)
	}
	if err := d.outbox.Write(ctx, tx, ev); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	// Final attribution for service incidents at resolution.
	if inc.ServiceID != "" && d.correlator != nil && (to == StatusResolved || to == StatusConfirmed) {
		if _, err := d.correlator.Run(ctx, inc); err != nil {
			return fmt.Errorf("detector: correlation: %w", err)
		}
	}
	return nil
}

// insertEvent records the initial transition event.
func (d *Detector) insertEvent(ctx context.Context, tx pgx.Tx, inc *Incident, from, to, reason string, meta map[string]any) error {
	_, err := tx.Exec(ctx, `INSERT INTO incident_events
		(id, incident_id, from_status, to_status, reason, actor_type, actor_id, metadata)
		VALUES ($1,$2,$3,$4,$5,'system','detector',$6)`,
		ids.NewUUID(), inc.ID, from, to, reason, string(mustJSON(meta)))
	return err
}

// isCandidate applies the candidate rule.
func (d *Detector) isCandidate(s targetStats) bool {
	return s.consecutiveFailures >= d.rules.ConsecutiveToCandidate ||
		s.failureRate >= d.rules.FailureRateToCandidate
}

// isConfirmed applies the confirmation rule.
func (d *Detector) isConfirmed(s targetStats) bool {
	return s.consecutiveFailures >= d.rules.ConsecutiveToConfirm ||
		s.failureRate >= d.rules.FailureRateToConfirm ||
		s.failingRegions >= d.rules.RegionsToConfirm
}

// describe builds the incident title/summary from target info + stats.
func (d *Detector) describe(ctx context.Context, ev checks.CheckEvent, s targetStats) (string, string) {
	name := d.targetName(ctx, ev.TargetType, ev.TargetID)
	kind := "service"
	if ev.TargetType == checks.TargetDependency {
		kind = "dependency"
	}
	if name == "" {
		name = ev.TargetID
	}
	title := fmt.Sprintf("%s degradation detected: %s", titleCase(kind), name)
	summary := fmt.Sprintf("%d consecutive failure(s), failure rate %.0f%% over the last %d observations from %d region(s)",
		s.consecutiveFailures, s.failureRate*100, d.rules.FailureRateWindow, s.failingRegions)
	return title, summary
}

// targetName resolves a human-readable name for the target.
func (d *Detector) targetName(ctx context.Context, targetType, targetID string) string {
	table := "services"
	if targetType == checks.TargetDependency {
		table = "dependencies"
	}
	var name string
	if err := d.pool.QueryRow(ctx, `SELECT name FROM `+table+` WHERE id=$1`, targetID).Scan(&name); err != nil {
		return ""
	}
	return name
}

// computeStats derives the decision inputs from a chronological series.
func computeStats(obs []checks.Observation, rules config.IncidentRulesConfig) targetStats {
	var st targetStats
	if len(obs) == 0 {
		return st
	}
	st.latestObservedAt = obs[len(obs)-1].ObservedAt
	// Consecutive failure/healthy runs from the newest observation backward.
	regions := map[string]bool{}
	failed := 0
	for i := len(obs) - 1; i >= 0; i-- {
		o := obs[i]
		regions[o.RegionID] = true
		if o.Availability {
			if st.consecutiveFailures == 0 {
				st.consecutiveHealthy++
			} else {
				break
			}
		} else {
			if st.consecutiveHealthy == 0 {
				st.consecutiveFailures++
			} else {
				break
			}
		}
	}
	// Failure rate over the last W observations.
	window := rules.FailureRateWindow
	if window <= 0 || window > len(obs) {
		window = len(obs)
	}
	for i := len(obs) - window; i < len(obs); i++ {
		if i < 0 {
			i = 0
		}
		if !obs[i].Availability {
			failed++
		}
	}
	st.failureRate = float64(failed) / float64(window)
	// Distinct failing regions across the whole lookback.
	failRegions := map[string]bool{}
	for _, o := range obs {
		if !o.Availability {
			failRegions[o.RegionID] = true
		}
	}
	st.failingRegions = len(failRegions)
	st.allRegions = len(regions)
	return st
}

func reverseObservations(obs []checks.Observation) []checks.Observation {
	out := make([]checks.Observation, len(obs))
	for i, o := range obs {
		out[len(obs)-1-i] = o
	}
	return out
}

func targetID(ev checks.CheckEvent, typ string) string {
	if ev.TargetType == typ {
		return ev.TargetID
	}
	return ""
}

func isNotFound(err error) bool { return errors.KindOf(err) == errors.KindNotFound }
