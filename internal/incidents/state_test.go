package incidents

import "testing"

func TestCanTransition(t *testing.T) {
	cases := []struct {
		from, to string
		want     bool
	}{
		{StatusCandidate, StatusConfirmed, true},
		{StatusCandidate, StatusFalsePositive, true},
		{StatusCandidate, StatusResolved, true},
		{StatusCandidate, StatusInvestigating, true},
		{StatusInvestigating, StatusConfirmed, true},
		{StatusInvestigating, StatusResolved, true},
		{StatusInvestigating, StatusFalsePositive, true},
		{StatusConfirmed, StatusResolved, true},
		{StatusResolved, StatusCandidate, false},
		{StatusResolved, StatusConfirmed, false},
		{StatusResolved, StatusFalsePositive, false},
		{StatusConfirmed, StatusCandidate, false},
		{StatusFalsePositive, StatusResolved, false},
		{StatusFalsePositive, StatusConfirmed, false},
		{"bogus", StatusResolved, false},
	}
	for _, c := range cases {
		if got := CanTransition(c.from, c.to); got != c.want {
			t.Errorf("CanTransition(%q,%q) = %v, want %v", c.from, c.to, got, c.want)
		}
	}
}

func TestComputeStats(t *testing.T) {
	// Not unit-testable without importing checks (package cycle); the
	// detector's rule logic is covered by the integration test.
}
