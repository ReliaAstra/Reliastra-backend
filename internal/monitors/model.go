// Package monitors defines monitors (WHAT to observe) and the executor
// interface used to run them. The HTTP executor lives here too; future
// monitor types (dns, tcp, browser, ...) plug into the same registry.
package monitors

import (
	"context"
	"encoding/json"
	"time"
)

// Supported monitor types (Phase 1 executes 'http'; others are rejected at
// creation until their executors land).
var SupportedTypes = []string{"http", "dns", "tcp", "browser", "webhook", "semantic"}

// ExecutableTypes are the types that actually run in Phase 1.
var ExecutableTypes = map[string]bool{"http": true}

// Monitor is a persisted monitor row.
type Monitor struct {
	ID              string          `json:"id"`
	ProjectID       string          `json:"project_id,omitempty"`
	OrganizationID  string          `json:"organization_id,omitempty"`
	ServiceID       string          `json:"service_id,omitempty"`
	DependencyID    string          `json:"dependency_id,omitempty"`
	VendorID        string          `json:"vendor_id,omitempty"`
	Name            string          `json:"name"`
	Type            string          `json:"type"`
	Target          string          `json:"target"`
	Configuration   json.RawMessage `json:"configuration"`
	IntervalSeconds int             `json:"interval_seconds"`
	TimeoutSeconds  int             `json:"timeout_seconds"`
	MaxAttempts     int             `json:"max_attempts"`
	Enabled         bool            `json:"enabled"`
	Visibility      string          `json:"visibility"`
	Status          string          `json:"status"`
	NextRunAt       time.Time       `json:"-"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
}

// HTTPConfig is the typed configuration of an http monitor.
type HTTPConfig struct {
	URL                     string            `json:"url"`
	Method                  string            `json:"method"`
	Headers                 map[string]string `json:"headers"`
	Body                    string            `json:"body"`
	ExpectedStatusCodes     []int             `json:"expected_status_codes"`
	TLSSkipVerify           bool              `json:"tls_skip_verify"` // false is the safe default
	ResponseBodyAssertions  []string          `json:"response_body_assertions"`
	ResponseHeaderAssertions map[string]string `json:"response_header_assertions"`
	LatencyThresholdMS      int               `json:"latency_threshold_ms"`
	RedirectPolicy          string            `json:"redirect_policy"` // follow | none
	BodySensitive           bool              `json:"body_sensitive"`
	SensitiveHeaders        []string          `json:"sensitive_headers"`
}

// DefaultHTTPConfig returns a valid baseline configuration.
func DefaultHTTPConfig() HTTPConfig {
	return HTTPConfig{
		Method:              "GET",
		ExpectedStatusCodes: []int{200},
		RedirectPolicy:      "follow",
	}
}

// RuntimeSpec is the fully-resolved configuration handed to an executor.
// Secrets are decrypted before building the spec and never logged.
type RuntimeSpec struct {
	MonitorID      string
	Type           string
	Target         string // human label (service/dependency name)
	HTTP           *HTTPConfig
	Secrets        map[string]string // header name -> value (sensitive)
	SecretBody     string            // sensitive request body
	Timeout        time.Duration
	MaxRedirects   int
	MaxResponseBytes int64
	RegionID       string
	ScheduledFor   time.Time
	Attempt        int
}

// CheckOutcome is the normalized outcome of a monitor execution.
type CheckOutcome struct {
	Success          bool
	StatusCode       int
	LatencyMS        int
	DNSMS            int
	ConnectMS        int
	TLSMS            int
	TTFBMS           int
	ErrorClass       string
	ErrorCode        string
	ErrorMessage     string
	ResponseSize     int64
	AssertionsPassed int
	AssertionsFailed int
	Metadata         map[string]any
}

// Executor executes a monitor of a specific type.
type Executor interface {
	// Type returns the monitor type this executor handles.
	Type() string
	// Validate checks a monitor configuration without executing it.
	Validate(config json.RawMessage) error
	// Execute runs the check and returns a normalized outcome.
	Execute(ctx context.Context, spec *RuntimeSpec) (*CheckOutcome, error)
}

// Registry maps monitor types to executors.
type Registry struct {
	executors map[string]Executor
}

// NewRegistry builds an executor registry.
func NewRegistry(executors ...Executor) *Registry {
	r := &Registry{executors: map[string]Executor{}}
	for _, e := range executors {
		r.executors[e.Type()] = e
	}
	return r
}

// Register adds an executor.
func (r *Registry) Register(e Executor) { r.executors[e.Type()] = e }

// Get returns the executor for a type, or nil.
func (r *Registry) Get(typ string) Executor { return r.executors[typ] }

// Supports reports whether the type can be executed.
func (r *Registry) Supports(typ string) bool {
	_, ok := r.executors[typ]
	return ok
}

// SupportedTypes returns the executable types (sorted, stable).
func (r *Registry) SupportedTypes() []string {
	var out []string
	for _, t := range SupportedTypes {
		if _, ok := r.executors[t]; ok {
			out = append(out, t)
		}
	}
	return out
}
