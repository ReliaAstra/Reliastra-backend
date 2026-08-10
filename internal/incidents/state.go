package incidents

import (
	"fmt"
)

// transitions is the incident state machine. Transitions not listed here are
// rejected; every allowed transition is auditable via incident_events.
var transitions = map[string]map[string]bool{
	StatusCandidate: {
		StatusInvestigating: true,
		StatusConfirmed:     true,
		StatusResolved:      true,
		StatusFalsePositive: true,
	},
	StatusInvestigating: {
		StatusConfirmed:     true,
		StatusResolved:      true,
		StatusFalsePositive: true,
	},
	StatusConfirmed: {
		StatusResolved: true,
	},
	StatusResolved:      {},
	StatusFalsePositive: {},
}

// CanTransition reports whether from -> to is allowed.
func CanTransition(from, to string) bool {
	if m, ok := transitions[from]; ok {
		return m[to]
	}
	return false
}

// ErrInvalidTransition is returned when a transition is not allowed.
type ErrInvalidTransition struct {
	From string
	To   string
}

func (e *ErrInvalidTransition) Error() string {
	return fmt.Sprintf("invalid incident transition: %s -> %s", e.From, e.To)
}
