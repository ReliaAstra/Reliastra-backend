package evidence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/incidents"
)

// Gatherer loads the data needed to build a canonical evidence package.
type Gatherer struct {
	pool         *pgxpool.Pool
	observations *checks.ObservationStore
	now          func() time.Time
}

// NewGatherer builds a Gatherer.
func NewGatherer(pool *pgxpool.Pool, observations *checks.ObservationStore) *Gatherer {
	return &Gatherer{pool: pool, observations: observations, now: time.Now}
}

// Build assembles the canonical evidence package for an incident.
// methodologyVersion/scoringVersion are recorded for reproducibility.
func (g *Gatherer) Build(ctx context.Context, inc *incidents.Incident, rec *EvidenceRecord,
	methodologyVersion, correlationVersion, scoringVersion string, maxObservations int) (*Package, error) {
	pkg := &Package{
		SchemaVersion:              "1.0",
		EvidenceID:                 rec.ID,
		Version:                    rec.Version,
		MethodologyVersion:         methodologyVersion,
		CorrelationAlgorithmVersion: correlationVersion,
		ScoringConfigVersion:       scoringVersion,
		GeneratedAt:                g.now().UTC().Format(time.RFC3339),
		Incident: IncidentSection{
			ID: inc.ID, Number: inc.Number, Status: inc.Status, Severity: inc.Severity,
			Title: inc.Title, Summary: inc.Summary,
			StartedAt: inc.StartedAt.UTC().Format(time.RFC3339),
			DetectedAt: inc.DetectedAt.UTC().Format(time.RFC3339),
		},
		Measurements: MeasurementsSection{
			Availability: map[string]float64{},
			AvgLatencyMS: map[string]float64{},
			StatusCodes:  map[string]int{},
			ErrorClasses: map[string]int{},
		},
		Timeline: []TimelineEntry{
			{At: inc.DetectedAt.UTC().Format(time.RFC3339), Event: "incident.detected",
				Detail: fmt.Sprintf("status=%s", inc.Status)},
		},
	}
	if inc.ResolvedAt != nil {
		pkg.Incident.ResolvedAt = inc.ResolvedAt.UTC().Format(time.RFC3339)
		pkg.Timeline = append(pkg.Timeline, TimelineEntry{
			At: inc.ResolvedAt.UTC().Format(time.RFC3339), Event: "incident.resolved"})
	}

	// Project / service / dependency names.
	pkg.Project = g.nameRef(ctx, "projects", inc.ProjectID)
	if inc.ServiceID != "" {
		pkg.Service = g.nameRefPtr(ctx, "services", inc.ServiceID)
	}
	if inc.DependencyID != "" {
		pkg.Dependency = g.nameRefPtr(ctx, "dependencies", inc.DependencyID)
	}

	// Observations within the incident window (start - pre, resolved + post).
	end := g.now().UTC()
	if inc.ResolvedAt != nil {
		end = inc.ResolvedAt.UTC()
	}
	from := inc.StartedAt.UTC().Add(-10 * time.Minute)
	to := end.Add(10 * time.Minute)

	targetType := checks.TargetDependency
	targetID := inc.DependencyID
	otherType := checks.TargetService
	otherID := inc.ServiceID
	if inc.ServiceID != "" {
		targetType, targetID = checks.TargetService, inc.ServiceID
		otherType, otherID = checks.TargetDependency, inc.DependencyID
	}

	mainObs, err := g.observations.RecentForTarget(ctx, targetType, targetID, from, to, maxObservations)
	if err != nil {
		return nil, err
	}
	var otherObs []checks.Observation
	if otherID != "" {
		otherObs, err = g.observations.RecentForTarget(ctx, otherType, otherID, from, to, maxObservations)
		if err != nil {
			return nil, err
		}
	}
	allObs := append(mainObs, otherObs...)

	// Timeline: first and last observations.
	if len(mainObs) > 0 {
		pkg.Timeline = append(pkg.Timeline,
			TimelineEntry{At: mainObs[0].ObservedAt.UTC().Format(time.RFC3339), Event: "observation.start"},
			TimelineEntry{At: mainObs[len(mainObs)-1].ObservedAt.UTC().Format(time.RFC3339), Event: "observation.end"},
		)
	}

	// Measurements per target.
	g.measure("service", mainObs, pkg)
	g.measure("dependency", otherObs, pkg)
	pkg.Measurements.TotalObservations = len(allObs)

	// Regions.
	pkg.Regions = g.regions(ctx, mainObs)

	// Observation ids (raw evidence references).
	for _, o := range mainObs {
		pkg.ObservationIDs = append(pkg.ObservationIDs, o.ID)
	}

	// Monitor snapshots.
	pkg.MonitorSnapshots = g.monitorSnapshots(ctx, inc)

	// Attribution from the incident + best correlation row.
	pkg.Attribution = g.attribution(ctx, inc)

	// Integrity (hash computed after the package is fully assembled).
	// The hash field is filled by HashPackage; we place a placeholder here.
	return pkg, nil
}

func (g *Gatherer) measure(key string, obs []checks.Observation, pkg *Package) {
	if len(obs) == 0 {
		return
	}
	failed := 0
	var latencySum int
	for _, o := range obs {
		if !o.Availability {
			failed++
		}
		latencySum += o.LatencyMS
		if sc, ok := o.Metadata["status_code"].(float64); ok && sc > 0 {
			pkg.Measurements.StatusCodes[fmt.Sprintf("%d", int(sc))]++
		}
		if o.FailureClass != "" {
			pkg.Measurements.ErrorClasses[o.FailureClass]++
		}
	}
	pkg.Measurements.Availability[key] = float64(len(obs)-failed) / float64(len(obs))
	pkg.Measurements.AvgLatencyMS[key] = float64(latencySum) / float64(len(obs))
}

func (g *Gatherer) regions(ctx context.Context, obs []checks.Observation) []RegionSection {
	byRegion := map[string]*RegionSection{}
	for _, o := range obs {
		r, ok := byRegion[o.RegionID]
		if !ok {
			r = &RegionSection{RegionID: o.RegionID, RegionName: g.regionName(ctx, o.RegionID)}
			byRegion[o.RegionID] = r
		}
		r.Observations++
		if !o.Availability {
			r.Failed++
		}
	}
	var out []RegionSection
	for _, r := range byRegion {
		if r.Observations > 0 {
			r.Availability = float64(r.Observations-r.Failed) / float64(r.Observations)
		}
		out = append(out, *r)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].RegionID < out[j].RegionID })
	return out
}

func (g *Gatherer) attribution(ctx context.Context, inc *incidents.Incident) *AttributionSection {
	if inc.AttributedDependencyID == "" {
		return nil
	}
	sec := &AttributionSection{
		DependencyID: inc.AttributedDependencyID,
		DependencyName: g.name(ctx, "dependencies", inc.AttributedDependencyID),
		Confidence:   inc.Confidence,
		EvidenceScore: inc.EvidenceScore,
		Factors:      map[string]float64{},
	}
	var temporal, regional, latency, errSim, failure, crit float64
	var expl []byte
	err := g.pool.QueryRow(ctx, `SELECT temporal_overlap, regional_overlap, latency_similarity,
		error_similarity, failure_overlap, criticality_weight, explanations
		FROM incident_correlations
		WHERE incident_id=$1 AND dependency_id=$2
		ORDER BY created_at DESC LIMIT 1`,
		inc.ID, nullableUUID(inc.AttributedDependencyID)).Scan(&temporal, &regional, &latency, &errSim, &failure, &crit, &expl)
	if err == nil {
		sec.Factors["temporal_overlap"] = temporal
		sec.Factors["regional_overlap"] = regional
		sec.Factors["latency_similarity"] = latency
		sec.Factors["error_similarity"] = errSim
		sec.Factors["failure_overlap"] = failure
		sec.Factors["criticality_weight"] = crit
		_ = json.Unmarshal(expl, &sec.Explanations)
	}
	return sec
}

func (g *Gatherer) monitorSnapshots(ctx context.Context, inc *incidents.Incident) []MonitorSnapshot {
	rows, err := g.pool.Query(ctx, `SELECT id, name, type, target, interval_seconds, timeout_seconds, configuration
		FROM monitors WHERE (service_id=$1 OR dependency_id=$2)`,
		nullableUUID(inc.ServiceID), nullableUUID(inc.DependencyID))
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []MonitorSnapshot
	for rows.Next() {
		var m MonitorSnapshot
		var config []byte
		if err := rows.Scan(&m.MonitorID, &m.Name, &m.Type, &m.Target,
			&m.IntervalSeconds, &m.TimeoutSeconds, &config); err != nil {
			return out
		}
		sum := sha256.Sum256(config)
		m.ConfigurationSHA = hex.EncodeToString(sum[:])
		out = append(out, m)
	}
	return out
}

func (g *Gatherer) name(ctx context.Context, table, id string) string {
	if id == "" {
		return ""
	}
	var name string
	if err := g.pool.QueryRow(ctx, `SELECT name FROM `+table+` WHERE id=$1`, id).Scan(&name); err != nil {
		return ""
	}
	return name
}

func (g *Gatherer) nameRef(ctx context.Context, table, id string) NameRef {
	return NameRef{ID: id, Name: g.name(ctx, table, id)}
}

func (g *Gatherer) nameRefPtr(ctx context.Context, table, id string) *NameRef {
	if id == "" {
		return nil
	}
	r := g.nameRef(ctx, table, id)
	return &r
}

func (g *Gatherer) regionName(ctx context.Context, id string) string {
	return g.name(ctx, "regions", id)
}

// nullableUUID returns nil for empty ids so uuid-typed parameters accept NULL
// instead of failing the cast with an empty string.
func nullableUUID(id string) any {
	if id == "" {
		return nil
	}
	return id
}
