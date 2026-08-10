// Package billing provides the entitlement/quota layer. Monitoring logic
// asks "is this organization allowed to do X?" via the Entitlements service —
// never "what does Stripe say?". The BillingProvider interface is the seam
// for a payment provider; Phase 1 uses the plan column on the organization.
package billing

import (
	"context"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
)

// BillingProvider answers plan questions for an organization. Replacements
// (Stripe, Chargebee, ...) implement this interface without touching domain
// logic.
type BillingProvider interface {
	// Plan returns the effective plan slug for an organization.
	Plan(ctx context.Context, organizationID string) (string, error)
}

// StaticProvider reads the plan from the organizations table.
type StaticProvider struct {
	store interface {
		PlanForOrg(ctx context.Context, orgID string) (string, error)
	}
}

// NewStaticProvider builds a provider backed by the organizations store.
func NewStaticProvider(s interface {
	PlanForOrg(ctx context.Context, orgID string) (string, error)
}) *StaticProvider {
	return &StaticProvider{store: s}
}

// Plan implements BillingProvider.
func (p *StaticProvider) Plan(ctx context.Context, organizationID string) (string, error) {
	return p.store.PlanForOrg(ctx, organizationID)
}

// Entitlements resolves plan limits and answers quota questions. All limits
// are configuration-driven (config.PlanConfig); no plan literals live in
// domain code.
type Entitlements struct {
	cfg config.PlanConfig
	// counts lets the service query current usage.
	counts UsageCounter
}

// UsageCounter reports current usage for quota checks.
type UsageCounter interface {
	CountMonitors(ctx context.Context, orgID string) (int, error)
	CountProjects(ctx context.Context, orgID string) (int, error)
	CountMembers(ctx context.Context, orgID string) (int, error)
	CountAPIKeys(ctx context.Context, orgID string) (int, error)
	CountEvidenceToday(ctx context.Context, orgID string) (int, error)
}

// NewEntitlements builds the entitlement service.
func NewEntitlements(cfg config.PlanConfig, counts UsageCounter) *Entitlements {
	return &Entitlements{cfg: cfg, counts: counts}
}

// Limits returns the limits for a plan (unknown plans fall back to free).
func (e *Entitlements) Limits(plan string) config.PlanLimits {
	if l, ok := e.cfg.Plans[plan]; ok {
		return l
	}
	return e.cfg.Plans[e.cfg.DefaultPlan]
}

// QuotaError is returned when a plan limit would be exceeded.
type QuotaError struct {
	Resource string
	Limit    int
}

func (e *QuotaError) Error() string {
	return "quota exceeded: " + e.Resource
}

// CanCreateMonitor checks the monitor quota.
func (e *Entitlements) CanCreateMonitor(ctx context.Context, plan string, orgID string) error {
	lim := e.Limits(plan)
	n, err := e.counts.CountMonitors(ctx, orgID)
	if err != nil {
		return err
	}
	if n >= lim.MaxMonitors {
		return &QuotaError{Resource: "monitors", Limit: lim.MaxMonitors}
	}
	return nil
}

// MinIntervalSeconds returns the minimum allowed check interval for a plan.
func (e *Entitlements) MinIntervalSeconds(plan string) int {
	return e.Limits(plan).MinIntervalSeconds
}

// CanCreateProject checks the project quota.
func (e *Entitlements) CanCreateProject(ctx context.Context, plan string, orgID string) error {
	lim := e.Limits(plan)
	n, err := e.counts.CountProjects(ctx, orgID)
	if err != nil {
		return err
	}
	if n >= lim.MaxProjects {
		return &QuotaError{Resource: "projects", Limit: lim.MaxProjects}
	}
	return nil
}

// CanAddMember checks the member quota.
func (e *Entitlements) CanAddMember(ctx context.Context, plan string, orgID string) error {
	lim := e.Limits(plan)
	n, err := e.counts.CountMembers(ctx, orgID)
	if err != nil {
		return err
	}
	if n >= lim.MaxMembers {
		return &QuotaError{Resource: "members", Limit: lim.MaxMembers}
	}
	return nil
}

// CanCreateAPIKey checks the API key quota.
func (e *Entitlements) CanCreateAPIKey(ctx context.Context, plan string, orgID string) error {
	lim := e.Limits(plan)
	n, err := e.counts.CountAPIKeys(ctx, orgID)
	if err != nil {
		return err
	}
	if n >= lim.MaxAPIKeys {
		return &QuotaError{Resource: "api_keys", Limit: lim.MaxAPIKeys}
	}
	return nil
}

// CanGenerateEvidence checks the daily evidence quota.
func (e *Entitlements) CanGenerateEvidence(ctx context.Context, plan string, orgID string) error {
	lim := e.Limits(plan)
	n, err := e.counts.CountEvidenceToday(ctx, orgID)
	if err != nil {
		return err
	}
	if n >= lim.MaxEvidencePerDay {
		return &QuotaError{Resource: "evidence", Limit: lim.MaxEvidencePerDay}
	}
	return nil
}
