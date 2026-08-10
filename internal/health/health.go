// Package health implements liveness and readiness checks.
//
// Liveness must never depend on PostgreSQL (a DB outage must not cause
// orchestrators to kill and restart the process, which would make recovery
// worse). Readiness reports dependency availability so load balancers can
// stop routing traffic.
package health

import (
	"context"
	"sync"
	"time"
)

// Checker reports dependency health.
type Checker struct {
	mu      sync.RWMutex
	checks  []NamedCheck
	results map[string]bool
}

// NamedCheck is a named readiness probe.
type NamedCheck struct {
	Name string
	Fn   func(ctx context.Context) error
}

// New creates a Checker.
func New() *Checker {
	return &Checker{results: map[string]bool{}}
}

// Register adds a readiness probe.
func (c *Checker) Register(name string, fn func(ctx context.Context) error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.checks = append(c.checks, NamedCheck{Name: name, Fn: fn})
}

// Status is a snapshot of health.
type Status struct {
	Live    bool              `json:"live"`
	Ready   bool              `json:"ready"`
	Checks  map[string]string `json:"checks,omitempty"` // name -> ok | error
}

// Live reports process liveness (always true while the process runs).
func (c *Checker) Live() Status {
	return Status{Live: true}
}

// Ready probes all registered dependencies with a short timeout.
func (c *Checker) Ready(ctx context.Context) Status {
	c.mu.RLock()
	checks := make([]NamedCheck, len(c.checks))
	copy(checks, c.checks)
	c.mu.RUnlock()

	st := Status{Live: true, Ready: true, Checks: map[string]string{}}
	probeCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	for _, ch := range checks {
		if err := ch.Fn(probeCtx); err != nil {
			st.Ready = false
			st.Checks[ch.Name] = "error: " + err.Error()
		} else {
			st.Checks[ch.Name] = "ok"
		}
	}
	return st
}
