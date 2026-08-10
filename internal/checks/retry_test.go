package checks

import (
	"math/rand"
	"testing"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/failure"
)

func TestShouldRetry(t *testing.T) {
	cases := []struct {
		class       string
		attempt     int
		maxAttempts int
		want        bool
	}{
		{string(failure.ConnectionTimeout), 1, 3, true},
		{string(failure.HTTP5xx), 1, 3, true},
		{string(failure.DNSFailure), 2, 3, true},
		{string(failure.HTTP4xx), 1, 3, false},
		{string(failure.AssertionFailed), 1, 3, false},
		{string(failure.SSRFBlocked), 1, 3, false},
		{string(failure.ConnectionTimeout), 3, 3, false}, // max attempts reached
	}
	for _, c := range cases {
		if got := ShouldRetry(c.class, c.attempt, c.maxAttempts); got != c.want {
			t.Errorf("ShouldRetry(%q,%d,%d) = %v, want %v", c.class, c.attempt, c.maxAttempts, got, c.want)
		}
	}
}

func TestRetryPolicyBackoff(t *testing.T) {
	p := NewRetryPolicy(1*time.Second, 10*time.Second, 5, rand.New(rand.NewSource(42)))
	prev := time.Duration(0)
	for i := 1; i <= 4; i++ {
		b := p.Backoff(i)
		if b <= prev {
			t.Errorf("backoff must grow: attempt %d -> %v (prev %v)", i, b, prev)
		}
		if b > 10*time.Second {
			t.Errorf("backoff must be capped at max: %v", b)
		}
		prev = b
	}
	// Cap check: huge attempt index still bounded.
	if b := p.Backoff(50); b > 10*time.Second {
		t.Errorf("backoff capped: %v", b)
	}
}
