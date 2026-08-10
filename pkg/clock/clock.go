// Package clock provides a small, swappable time source so that tests can
// control time deterministically without global mutable state.
package clock

import (
	"sync"
	"time"
)

// Clock is the interface every time-dependent component should use.
type Clock interface {
	// Now returns the current time in UTC.
	Now() time.Time
}

type systemClock struct{}

func (systemClock) Now() time.Time { return time.Now().UTC() }

// System returns the real wall clock.
func System() Clock { return systemClock{} }

// Fixed returns a clock that always reports t (for deterministic tests).
func Fixed(t time.Time) Clock { return fixedClock{t} }

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t.UTC() }

// Mutable returns a thread-safe clock whose value can be advanced from tests.
type Mutable struct {
	mu sync.RWMutex
	t  time.Time
}

func (m *Mutable) Now() time.Time {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.t.UTC()
}

// Advance moves the clock forward by d.
func (m *Mutable) Advance(d time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.t = m.t.Add(d)
}

// Set replaces the clock time.
func (m *Mutable) Set(t time.Time) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.t = t
}

// NewMutable creates a Mutable clock starting at t.
func NewMutable(t time.Time) *Mutable { return &Mutable{t: t} }
