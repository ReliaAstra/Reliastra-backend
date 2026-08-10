# Correlation algorithm (deterministic v1)

## Design principles

- **Deterministic + explainable + testable.** No LLM, no opaque statistics.
  Every conclusion can be explained by "X, Y and Z factors".
- **Versioned.** Every persisted result records
  `correlation_version = "v1"` and `scoring_config_version = "v1"`, so any
  historical conclusion is reproducible.
- **Substitution boundary.** The incident engine depends on the
  `incidents.Correlator` interface; `RuleBasedCorrelator` is the Phase 1
  implementation. A `StatisticalCorrelator`, `MLCorrelator` or
  `HybridCorrelator` can replace it without touching the incident engine.

## Inputs

For a service incident:

- The incident (service id, window: started_at − pre, resolved_at + post).
- The service's observations in the window (normalized observations, never
  raw HTTP details).
- Observations for every dependency linked via `service_dependencies`.
- Relationship criticality per dependency.

## Factors (all normalized to [0,1])

| Factor | Definition |
|---|---|
| `temporal_overlap` | Share of the service's failing time-buckets (60 s) where the dependency was also failing |
| `regional_overlap` | Share of regions observing service failure that also observed dependency failure |
| `latency_similarity` | Pearson correlation of per-bucket mean latency between service and dependency, clamped to [0,1]; neutral 0.5 with insufficient data |
| `error_similarity` | `1 − |service_failure_rate − dependency_failure_rate|` |
| `failure_overlap` | Fraction of service failure observations within ±2 buckets of a dependency failure observation |

## Scoring

```
raw = w_t·temporal + w_r·regional + w_l·latency + w_e·error + w_f·failure
score = clamp01(raw × criticality_weight)
```

Weights (sum to 1): temporal 0.35, regional 0.20, latency 0.15, error 0.15,
failure 0.15.

Criticality multiplier: critical 1.0, high 0.9, medium 0.75, low 0.6.

Confidence mapping: `≥0.75 high`, `≥0.55 medium`, `≥0.35 low`, else `none`.

Attribution: the top-scoring dependency is attributed **only if** its score
≥ `attribution_threshold` (0.55). Otherwise the incident has `confidence =
none` and no attributed dependency — an honest "we cannot tell" outcome.

Every weight and threshold lives in `correlation.ScoringConfig`; there are no
magic numbers in engine code.

## Output

One `incident_correlations` row per (incident, dependency):

- all factors, the evidence score, confidence
- `service_failure_rate`, `dependency_failure_rate`
- human-readable `explanations` (e.g. "Dependency failure overlapped 94% of
  the incident's failing buckets", "Regional overlap: 3/3 regions")
- `window_start`, `window_end`, algorithm + scoring versions

The attributed dependency + confidence + score are also written onto the
incident row.

## Reproducibility

Evidence packages embed `correlation_algorithm_version`,
`scoring_config_version`, monitor configuration snapshots, region
configuration snapshots, observation ids and generation timestamp, so a
historical conclusion can be re-derived and audited even after
configuration changes.
