package monitors

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/billing"
	apperrors "github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

// Service contains monitor business rules (validation, quotas, runtime spec
// assembly). It depends on the executor registry and entitlements, never on
// HTTP handlers.
type Service struct {
	store   *Store
	reg     *Registry
	ent     *billing.Entitlements
	billing billing.BillingProvider
	worker  WorkerConfig
}

// WorkerConfig carries execution limits the service needs at spec-build time.
type WorkerConfig struct {
	MaxResponseBytes int64
	MaxRedirects     int
}

// NewService builds the monitor service.
func NewService(store *Store, reg *Registry, ent *billing.Entitlements,
	billing billing.BillingProvider, worker WorkerConfig) *Service {
	return &Service{store: store, reg: reg, ent: ent, billing: billing, worker: worker}
}

// CreateInput is the validated request to create a monitor.
type CreateInput struct {
	ProjectID       string
	ServiceID       string
	DependencyID    string
	Name            string
	Type            string
	Target          string
	Configuration   json.RawMessage
	IntervalSeconds int
	TimeoutSeconds  int
	MaxAttempts     int
	RegionIDs       []string
	Enabled         bool
	Secrets         map[string]string
	SecretBody      string
}

// Create validates and persists a customer monitor.
func (s *Service) Create(ctx context.Context, orgID string, in CreateInput) (*Monitor, error) {
	if in.Name == "" || len(in.Name) > 120 {
		return nil, apperrors.Validation("invalid_name", "monitor name must be 1-120 characters", nil)
	}
	if in.Type == "" {
		in.Type = "http"
	}
	if !s.reg.Supports(in.Type) {
		return nil, apperrors.Validation("unsupported_type",
			fmt.Sprintf("monitor type %q is not supported yet", in.Type),
			map[string]any{"supported": s.reg.SupportedTypes()})
	}
	if in.IntervalSeconds < 10 {
		return nil, apperrors.Validation("invalid_interval", "minimum check interval is 10 seconds", nil)
	}
	if in.TimeoutSeconds < 1 || in.TimeoutSeconds > 120 {
		return nil, apperrors.Validation("invalid_timeout", "timeout must be between 1 and 120 seconds", nil)
	}
	if in.MaxAttempts < 1 || in.MaxAttempts > 10 {
		return nil, apperrors.Validation("invalid_max_attempts", "max_attempts must be between 1 and 10", nil)
	}
	ex := s.reg.Get(in.Type)
	if ex == nil {
		return nil, apperrors.Validation("unsupported_type", "monitor type is not executable", nil)
	}
	if in.Configuration == nil || len(in.Configuration) == 0 {
		def := DefaultHTTPConfig()
		raw, _ := json.Marshal(def)
		in.Configuration = raw
	}
	if err := ex.Validate(in.Configuration); err != nil {
		return nil, apperrors.Validation("invalid_configuration", err.Error(), nil)
	}

	plan, err := s.billing.Plan(ctx, orgID)
	if err != nil {
		return nil, err
	}
	if err := s.ent.CanCreateMonitor(ctx, plan, orgID); err != nil {
		return nil, quotaError(err)
	}
	if min := s.ent.MinIntervalSeconds(plan); in.IntervalSeconds < min {
		return nil, apperrors.Validation("interval_too_frequent",
			fmt.Sprintf("this plan requires a check interval of at least %d seconds", min), nil)
	}

	m := &Monitor{
		ProjectID: in.ProjectID, ServiceID: in.ServiceID, DependencyID: in.DependencyID,
		Name: in.Name, Type: in.Type, Target: in.Target,
		Configuration: in.Configuration, IntervalSeconds: in.IntervalSeconds,
		TimeoutSeconds: in.TimeoutSeconds, MaxAttempts: in.MaxAttempts, Enabled: in.Enabled,
	}
	return s.store.Create(ctx, orgID, m, in.RegionIDs, in.Secrets, in.SecretBody)
}

// UpdateInput patches a monitor.
type UpdateInput struct {
	Name            *string
	Target          *string
	Configuration   json.RawMessage
	IntervalSeconds *int
	TimeoutSeconds  *int
	MaxAttempts     *int
	Enabled         *bool
	RegionIDs       []string // nil = unchanged
	Secrets         map[string]string
	SecretBody      string
}

// Update validates and persists changes.
func (s *Service) Update(ctx context.Context, orgID, id string, in UpdateInput) (*Monitor, error) {
	existing, err := s.store.ByID(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	patch := map[string]any{}
	if in.Name != nil {
		if *in.Name == "" {
			return nil, apperrors.Validation("invalid_name", "name must not be empty", nil)
		}
		patch["name"] = *in.Name
	}
	if in.Target != nil {
		patch["target"] = *in.Target
	}
	if len(in.Configuration) > 0 {
		ex := s.reg.Get(existing.Type)
		if ex == nil {
			return nil, apperrors.Validation("unsupported_type", "monitor type is not executable", nil)
		}
		if err := ex.Validate(in.Configuration); err != nil {
			return nil, apperrors.Validation("invalid_configuration", err.Error(), nil)
		}
		patch["configuration"] = in.Configuration
	}
	if in.IntervalSeconds != nil {
		if *in.IntervalSeconds < 10 {
			return nil, apperrors.Validation("invalid_interval", "minimum check interval is 10 seconds", nil)
		}
		plan, err := s.billing.Plan(ctx, orgID)
		if err != nil {
			return nil, err
		}
		if min := s.ent.MinIntervalSeconds(plan); *in.IntervalSeconds < min {
			return nil, apperrors.Validation("interval_too_frequent",
				fmt.Sprintf("this plan requires a check interval of at least %d seconds", min), nil)
		}
		patch["interval_seconds"] = *in.IntervalSeconds
	}
	if in.TimeoutSeconds != nil {
		if *in.TimeoutSeconds < 1 || *in.TimeoutSeconds > 120 {
			return nil, apperrors.Validation("invalid_timeout", "timeout must be between 1 and 120 seconds", nil)
		}
		patch["timeout_seconds"] = *in.TimeoutSeconds
	}
	if in.MaxAttempts != nil {
		if *in.MaxAttempts < 1 || *in.MaxAttempts > 10 {
			return nil, apperrors.Validation("invalid_max_attempts", "max_attempts must be between 1 and 10", nil)
		}
		patch["max_attempts"] = *in.MaxAttempts
	}
	if in.Enabled != nil {
		patch["enabled"] = *in.Enabled
	}
	return s.store.Update(ctx, orgID, id, patch, in.RegionIDs, in.Secrets, in.SecretBody)
}

// Delete removes a monitor.
func (s *Service) Delete(ctx context.Context, orgID, id string) error {
	return s.store.Delete(ctx, orgID, id)
}

// List returns customer monitors for an org (optional filters).
func (s *Service) List(ctx context.Context, orgID, projectID string, enabled *bool) ([]Monitor, error) {
	return s.store.List(ctx, orgID, projectID, enabled)
}

// Get returns one customer monitor for an org.
func (s *Service) Get(ctx context.Context, orgID, id string) (*Monitor, error) {
	return s.store.ByID(ctx, orgID, id)
}

// Regions returns the region ids assigned to a monitor.
func (s *Service) Regions(ctx context.Context, monitorID string) ([]string, error) {
	return s.store.Regions(ctx, monitorID)
}

// BuildRuntimeSpec assembles the executor input for a monitor, decrypting
// secrets. Never logs the decrypted values.
func (s *Service) BuildRuntimeSpec(ctx context.Context, m *Monitor, regionID string, scheduledFor time.Time, attempt int) (*RuntimeSpec, error) {
	if m.Type != "http" {
		return nil, fmt.Errorf("monitor type %q not executable", m.Type)
	}
	var cfg HTTPConfig
	if err := json.Unmarshal(m.Configuration, &cfg); err != nil {
		return nil, apperrors.Internal("invalid_stored_config", "stored monitor configuration is invalid")
	}
	headers, secretBody, err := s.store.DecryptSecrets(ctx, m.ID)
	if err != nil {
		return nil, err
	}
	return &RuntimeSpec{
		MonitorID:        m.ID,
		Type:             m.Type,
		Target:           m.Target,
		HTTP:             &cfg,
		Secrets:          headers,
		SecretBody:       secretBody,
		Timeout:          time.Duration(m.TimeoutSeconds) * time.Second,
		MaxRedirects:     s.worker.MaxRedirects,
		MaxResponseBytes: s.worker.MaxResponseBytes,
		RegionID:         regionID,
		ScheduledFor:     scheduledFor,
		Attempt:          attempt,
	}, nil
}

func quotaError(err error) error {
	var qe *billing.QuotaError
	if errors.As(err, &qe) {
		return apperrors.Conflict("quota_exceeded",
			fmt.Sprintf("plan limit reached: %s (max %d)", qe.Resource, qe.Limit))
	}
	return err
}
