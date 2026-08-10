package correlation

import (
	"math"
	"testing"
)

func TestConfidenceFor(t *testing.T) {
	cfg := DefaultScoringConfig()
	cases := []struct {
		score float64
		want  string
	}{
		{0.80, "high"},
		{0.75, "high"},
		{0.60, "medium"},
		{0.55, "medium"},
		{0.40, "low"},
		{0.35, "low"},
		{0.10, "none"},
	}
	for _, c := range cases {
		if got := cfg.ConfidenceFor(c.score); got != c.want {
			t.Errorf("ConfidenceFor(%v) = %q, want %q", c.score, got, c.want)
		}
	}
}

func TestCriticalityWeight(t *testing.T) {
	cfg := DefaultScoringConfig()
	if cfg.CriticalityWeight("critical") != 1.0 {
		t.Error("critical weight must be 1.0")
	}
	if cfg.CriticalityWeight("bogus") != cfg.CriticalityMedium {
		t.Error("unknown criticality must fall back to medium")
	}
}

func TestPearsonAndClamp(t *testing.T) {
	xs := []float64{1, 2, 3, 4, 5}
	ys := []float64{2, 4, 6, 8, 10}
	if r := pearson(xs, ys); math.Abs(r-1) > 1e-9 {
		t.Errorf("perfect correlation expected 1, got %v", r)
	}
	ys = []float64{10, 8, 6, 4, 2}
	if r := pearson(xs, ys); math.Abs(r+1) > 1e-9 {
		t.Errorf("perfect anti-correlation expected -1, got %v", r)
	}
	if v := clamp(1.5); v != 1 {
		t.Errorf("clamp(1.5) = %v", v)
	}
	if v := clamp(-0.2); v != 0 {
		t.Errorf("clamp(-0.2) = %v", v)
	}
}

func TestLatencySimilarityNeutral(t *testing.T) {
	// Insufficient shared buckets -> neutral 0.5.
	if v := latencySimilarity(&timeSeries{}, &timeSeries{}); v != 0.5 {
		t.Errorf("empty series should be neutral, got %v", v)
	}
}
