package checks

import (
	"math/rand"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/failure"
)

// RetryPolicy computes retry backoff for job attempts. Exponential backoff
// with jitter, capped at a maximum delay. The policy is configuration-free at
// call time (values injected from config), deterministic given the attempt
// number except for ±20% jitter.
type RetryPolicy struct {
	Base     time.Duration
	Max      time.Duration
	MaxAttempts int
	rng      *rand.Rand
}

// NewRetryPolicy builds a policy. rng may be nil (defaults to a process-local
// source); jitter never affects correctness, only timing spread.
func NewRetryPolicy(base, max time.Duration, maxAttempts int, rng *rand.Rand) *RetryPolicy {
	if rng == nil {
		rng = rand.New(rand.NewSource(time.Now().UnixNano()))
	}
	return &RetryPolicy{Base: base, Max: max, MaxAttempts: maxAttempts, rng: rng}
}

// Backoff returns the delay before the next attempt after a failure on
// attempt (1-based). Exponential: base * 2^(attempt-1), capped, ±20% jitter.
func (p *RetryPolicy) Backoff(attempt int) time.Duration {
	if p.Base <= 0 {
		p.Base = 30 * time.Second
	}
	if p.Max <= 0 {
		p.Max = 30 * time.Minute
	}
	exp := p.Base
	for i := 1; i < attempt; i++ {
		exp *= 2
		if exp >= p.Max {
			exp = p.Max
			break
		}
	}
	if exp > p.Max {
		exp = p.Max
	}
	// ±20% jitter.
	factor := 0.8 + p.rng.Float64()*0.4
	return time.Duration(float64(exp) * factor)
}

// ShouldRetry decides whether a failed execution with class c should be
// retried given the current attempt and max attempts.
func ShouldRetry(class string, attempt, maxAttempts int) bool {
	if attempt >= maxAttempts {
		return false
	}
	return failure.Retryable(failure.Class(class))
}
