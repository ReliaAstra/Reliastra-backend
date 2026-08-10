package correlation

import "math"

// ScoringConfig centralizes every weight and threshold used by the v1
// algorithm. No magic numbers live in engine code.
type ScoringConfig struct {
	// Weights (must sum to 1).
	WeightTemporal float64
	WeightRegional float64
	WeightLatency  float64
	WeightError    float64
	WeightFailure  float64
	// Criticality multipliers.
	CriticalityCritical float64
	CriticalityHigh     float64
	CriticalityMedium   float64
	CriticalityLow      float64
	// Confidence thresholds.
	HighThreshold  float64
	MediumThreshold float64
	LowThreshold   float64
	// Attribution threshold: below this, no dependency is attributed.
	AttributionThreshold float64
	// Window padding before/after the incident.
	PreWindowMinutes  float64
	PostWindowMinutes float64
	// Bucket size for time-series alignment (seconds).
	BucketSeconds int
}

// DefaultScoringConfig returns the v1 defaults.
func DefaultScoringConfig() ScoringConfig {
	return ScoringConfig{
		WeightTemporal: 0.35,
		WeightRegional: 0.20,
		WeightLatency:  0.15,
		WeightError:    0.15,
		WeightFailure:  0.15,
		CriticalityCritical: 1.0,
		CriticalityHigh:     0.9,
		CriticalityMedium:   0.75,
		CriticalityLow:      0.6,
		HighThreshold:       0.75,
		MediumThreshold:     0.55,
		LowThreshold:        0.35,
		AttributionThreshold: 0.55,
		PreWindowMinutes:    5,
		PostWindowMinutes:   5,
		BucketSeconds:       60,
	}
}

// ConfidenceFor maps a score to low/medium/high.
func (c ScoringConfig) ConfidenceFor(score float64) string {
	switch {
	case score >= c.HighThreshold:
		return "high"
	case score >= c.MediumThreshold:
		return "medium"
	case score >= c.LowThreshold:
		return "low"
	default:
		return "none"
	}
}

// CriticalityWeight returns the multiplier for a criticality level.
func (c ScoringConfig) CriticalityWeight(criticality string) float64 {
	switch criticality {
	case "critical":
		return c.CriticalityCritical
	case "high":
		return c.CriticalityHigh
	case "medium":
		return c.CriticalityMedium
	case "low":
		return c.CriticalityLow
	}
	return c.CriticalityMedium
}

// clamp keeps values in [0,1].
func clamp(v float64) float64 { return math.Max(0, math.Min(1, v)) }
