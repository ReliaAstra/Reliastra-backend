// Package correlation implements the Phase 1 deterministic correlation
// engine. Attribution is explainable and reproducible: the algorithm version
// and scoring configuration version are recorded with every result, and
// every factor's contribution is described in human-readable explanations.
//
// No statistical/ML models are used in Phase 1. The incidents.Correlator
// interface is the substitution boundary for future Statistical/ML/Hybrid
// implementations.
package correlation

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/dependencies"
	"github.com/ReliaAstra/reliastra-backend/internal/incidents"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// AlgorithmVersion is the version of the deterministic algorithm.
const AlgorithmVersion = "v1"

// ScoringConfigVersion identifies this scoring configuration.
const ScoringConfigVersion = "v1"

// DataProviders gathers everything the rule-based correlator needs.
type DataProviders struct {
	Pool         *pgxpool.Pool
	Observations *checks.ObservationStore
	Dependencies *dependencies.Store
	Incidents    *incidents.Store
	TimeNow      func() time.Time
}

// RuleBasedCorrelator is the deterministic v1 engine.
type RuleBasedCorrelator struct {
	pool         *pgxpool.Pool
	observations *checks.ObservationStore
	deps         *dependencies.Store
	incidents    *incidents.Store
	cfg          ScoringConfig
	now          func() time.Time
}

// NewRuleBased builds the v1 correlator.
func NewRuleBased(p DataProviders) *RuleBasedCorrelator {
	now := p.TimeNow
	if now == nil {
		now = time.Now
	}
	return &RuleBasedCorrelator{
		pool: p.Pool, observations: p.Observations, deps: p.Dependencies,
		incidents: p.Incidents, cfg: DefaultScoringConfig(), now: now,
	}
}

// Config exposes the active scoring configuration (for evidence/docs).
func (c *RuleBasedCorrelator) Config() ScoringConfig { return c.cfg }

// Run implements incidents.Correlator. Only service incidents are correlated;
// the incident's linked dependencies are evaluated over a padded window.
func (c *RuleBasedCorrelator) Run(ctx context.Context, inc *incidents.Incident) ([]incidents.CorrelationResult, error) {
	if inc.ServiceID == "" {
		return nil, nil // dependency incidents are not correlated in v1
	}
	end := c.now().UTC()
	if inc.ResolvedAt != nil {
		end = inc.ResolvedAt.UTC()
	}
	pre := time.Duration(c.cfg.PreWindowMinutes*60) * time.Second
	post := time.Duration(c.cfg.PostWindowMinutes*60) * time.Second
	windowStart := inc.StartedAt.UTC().Add(-pre)
	windowEnd := end.Add(post)

	linked, err := c.deps.LinkedForService(ctx, inc.ServiceID)
	if err != nil {
		return nil, fmt.Errorf("correlation: linked dependencies: %w", err)
	}
	if len(linked) == 0 {
		return nil, nil
	}

	limit := 5000
	svcObs, err := c.observations.RecentForTarget(ctx, checks.TargetService, inc.ServiceID, windowStart, windowEnd, limit)
	if err != nil {
		return nil, fmt.Errorf("correlation: service observations: %w", err)
	}

	var results []incidents.CorrelationResult
	for _, ld := range linked {
		depObs, err := c.observations.RecentForTarget(ctx, checks.TargetDependency, ld.ID, windowStart, windowEnd, limit)
		if err != nil {
			return nil, fmt.Errorf("correlation: dependency observations: %w", err)
		}
		res := c.evaluate(inc, ld, svcObs, depObs, windowStart, windowEnd)
		if err := c.persist(ctx, inc.ID, res); err != nil {
			return nil, err
		}
		results = append(results, res)
	}

	sort.Slice(results, func(i, j int) bool {
		if results[i].EvidenceScore != results[j].EvidenceScore {
			return results[i].EvidenceScore > results[j].EvidenceScore
		}
		return results[i].CriticalityWeight > results[j].CriticalityWeight
	})

	// Attribute the best dependency if it clears the threshold.
	if len(results) > 0 && results[0].EvidenceScore >= c.cfg.AttributionThreshold {
		if err := c.attribute(ctx, inc.ID, results[0]); err != nil {
			return results, err
		}
	}
	return results, nil
}

// evaluate computes the v1 factor breakdown for one dependency.
func (c *RuleBasedCorrelator) evaluate(inc *incidents.Incident, ld dependencies.LinkedDependency,
	svcObs, depObs []checks.Observation, windowStart, windowEnd time.Time) incidents.CorrelationResult {

	svcSeries := buildSeries(svcObs, c.cfg.BucketSeconds)
	depSeries := buildSeries(depObs, c.cfg.BucketSeconds)

	svcRate := failureRate(svcObs)
	depRate := failureRate(depObs)

	svcFailBuckets := failingBuckets(svcSeries)
	depFailBuckets := failingBuckets(depSeries)
	temporal := 0.0
	if len(svcFailBuckets) > 0 {
		both := 0
		for b := range svcFailBuckets {
			if depFailBuckets[b] {
				both++
			}
		}
		temporal = float64(both) / float64(len(svcFailBuckets))
	}

	regional := regionalOverlap(svcObs, depObs)
	latencySim := latencySimilarity(svcSeries, depSeries)
	errorSim := 1 - math.Abs(svcRate-depRate)
	failureOverlap := failureProximity(svcObs, depObs, time.Duration(2*c.cfg.BucketSeconds)*time.Second)

	criticalityWeight := c.cfg.CriticalityWeight(ld.Criticality)

	raw := c.cfg.WeightTemporal*temporal +
		c.cfg.WeightRegional*regional +
		c.cfg.WeightLatency*latencySim +
		c.cfg.WeightError*errorSim +
		c.cfg.WeightFailure*failureOverlap
	score := clamp(raw * criticalityWeight)

	explanations := []string{
		fmt.Sprintf("Dependency failure overlapped %.0f%% of the incident's failing buckets", temporal*100),
		fmt.Sprintf("Regional overlap: %.0f%% of regions observing service failure also observed dependency failure", regional*100),
		fmt.Sprintf("Service failure rate %.0f%% vs dependency failure rate %.0f%%", svcRate*100, depRate*100),
		fmt.Sprintf("Latency similarity %.0f%%", latencySim*100),
		fmt.Sprintf("Criticality weight %.2f (relationship: %s)", criticalityWeight, ld.Criticality),
	}

	return incidents.CorrelationResult{
		IncidentID: inc.ID, DependencyID: ld.ID,
		CorrelationVersion:   AlgorithmVersion,
		ScoringConfigVersion: ScoringConfigVersion,
		EvidenceScore:        math.Round(score*1000) / 1000,
		Confidence:           c.cfg.ConfidenceFor(score),
		TemporalOverlap:      round2(temporal),
		RegionalOverlap:      round2(regional),
		LatencySimilarity:    round2(latencySim),
		ErrorSimilarity:      round2(errorSim),
		FailureOverlap:       round2(failureOverlap),
		CriticalityWeight:    criticalityWeight,
		ServiceFailureRate:   round2(svcRate),
		DependencyFailureRate: round2(depRate),
		Explanations:         explanations,
		WindowStart:          windowStart,
		WindowEnd:            windowEnd,
	}
}

// persist upserts the correlation row.
func (c *RuleBasedCorrelator) persist(ctx context.Context, incidentID string, r incidents.CorrelationResult) error {
	expl, _ := json.Marshal(r.Explanations)
	_, err := c.pool.Exec(ctx, `
		INSERT INTO incident_correlations
			(id, incident_id, dependency_id, correlation_version, scoring_config_version,
			 evidence_score, confidence, temporal_overlap, regional_overlap,
			 latency_similarity, error_similarity, failure_overlap, criticality_weight,
			 service_failure_rate, dependency_failure_rate, explanations, window_start, window_end)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
		ON CONFLICT (incident_id, dependency_id) DO UPDATE SET
			evidence_score=EXCLUDED.evidence_score, confidence=EXCLUDED.confidence,
			temporal_overlap=EXCLUDED.temporal_overlap, regional_overlap=EXCLUDED.regional_overlap,
			latency_similarity=EXCLUDED.latency_similarity, error_similarity=EXCLUDED.error_similarity,
			failure_overlap=EXCLUDED.failure_overlap, criticality_weight=EXCLUDED.criticality_weight,
			service_failure_rate=EXCLUDED.service_failure_rate,
			dependency_failure_rate=EXCLUDED.dependency_failure_rate,
			explanations=EXCLUDED.explanations, window_start=EXCLUDED.window_start,
			window_end=EXCLUDED.window_end, created_at=now()`,
		ids.NewUUID(), incidentID, r.DependencyID, r.CorrelationVersion, r.ScoringConfigVersion,
		r.EvidenceScore, r.Confidence, r.TemporalOverlap, r.RegionalOverlap,
		r.LatencySimilarity, r.ErrorSimilarity, r.FailureOverlap, r.CriticalityWeight,
		r.ServiceFailureRate, r.DependencyFailureRate, string(expl), r.WindowStart, r.WindowEnd)
	return err
}

// attribute records the top dependency on the incident.
func (c *RuleBasedCorrelator) attribute(ctx context.Context, incidentID string, r incidents.CorrelationResult) error {
	tx, err := c.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if err := c.incidents.UpdateAttribution(ctx, tx, incidentID, r.DependencyID, r.Confidence, r.CorrelationVersion, r.EvidenceScore); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// timeSeries maps bucket -> per-bucket aggregate.
type timeSeries struct {
	bucketSeconds int
	failure       map[int64]bool
	latencies     map[int64][]int
}

func buildSeries(obs []checks.Observation, bucketSeconds int) *timeSeries {
	ts := &timeSeries{
		bucketSeconds: bucketSeconds,
		failure:       map[int64]bool{},
		latencies:     map[int64][]int{},
	}
	for _, o := range obs {
		b := o.ObservedAt.Unix() / int64(bucketSeconds)
		if !o.Availability {
			ts.failure[b] = true
		}
		ts.latencies[b] = append(ts.latencies[b], o.LatencyMS)
	}
	return ts
}

func failingBuckets(ts *timeSeries) map[int64]bool {
	if ts == nil {
		return map[int64]bool{}
	}
	return ts.failure
}

func failureRate(obs []checks.Observation) float64 {
	if len(obs) == 0 {
		return 0
	}
	failed := 0
	for _, o := range obs {
		if !o.Availability {
			failed++
		}
	}
	return float64(failed) / float64(len(obs))
}

func regionalOverlap(svcObs, depObs []checks.Observation) float64 {
	svcRegions := map[string]bool{}
	depRegions := map[string]bool{}
	for _, o := range svcObs {
		if !o.Availability {
			svcRegions[o.RegionID] = true
		}
	}
	for _, o := range depObs {
		if !o.Availability {
			depRegions[o.RegionID] = true
		}
	}
	if len(svcRegions) == 0 {
		return 0
	}
	both := 0
	for r := range svcRegions {
		if depRegions[r] {
			both++
		}
	}
	return float64(both) / float64(len(svcRegions))
}

func latencySimilarity(svc, dep *timeSeries) float64 {
	xs, ys := []float64{}, []float64{}
	for b, lats := range svc.latencies {
		if depLats, ok := dep.latencies[b]; ok {
			xs = append(xs, mean(lats))
			ys = append(ys, mean(depLats))
		}
	}
	if len(xs) < 2 {
		return 0.5 // neutral with insufficient data
	}
	r := pearson(xs, ys)
	if math.IsNaN(r) {
		return 0.5
	}
	return clamp(r)
}

func failureProximity(svcObs, depObs []checks.Observation, tolerance time.Duration) float64 {
	var depFailTimes []time.Time
	for _, o := range depObs {
		if !o.Availability {
			depFailTimes = append(depFailTimes, o.ObservedAt)
		}
	}
	if len(depFailTimes) == 0 {
		return 0
	}
	svcFails := 0
	near := 0
	for _, o := range svcObs {
		if o.Availability {
			continue
		}
		svcFails++
		for _, t := range depFailTimes {
			d := o.ObservedAt.Sub(t)
			if d < 0 {
				d = -d
			}
			if d <= tolerance {
				near++
				break
			}
		}
	}
	if svcFails == 0 {
		return 0
	}
	return float64(near) / float64(svcFails)
}

func mean(xs []int) float64 {
	if len(xs) == 0 {
		return 0
	}
	s := 0
	for _, v := range xs {
		s += v
	}
	return float64(s) / float64(len(xs))
}

func pearson(xs, ys []float64) float64 {
	n := len(xs)
	if n != len(ys) || n == 0 {
		return math.NaN()
	}
	var sx, sy, sxx, syy, sxy float64
	for i := 0; i < n; i++ {
		sx += xs[i]
		sy += ys[i]
		sxx += xs[i] * xs[i]
		syy += ys[i] * ys[i]
		sxy += xs[i] * ys[i]
	}
	den := math.Sqrt((float64(n)*sxx - sx*sx) * (float64(n)*syy - sy*sy))
	if den == 0 {
		return math.NaN()
	}
	return (float64(n)*sxy - sx*sy) / den
}

func round2(v float64) float64 { return math.Round(v*100) / 100 }
