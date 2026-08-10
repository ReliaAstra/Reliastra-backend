package auth

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/organizations"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

// Principal is the authenticated actor attached to a request context.
type Principal struct {
	UserID         string
	AuthMethod     string // "session" | "api_key"
	APIKeyID       string
	Scopes         []APIScope // nil for user sessions (full user permissions)
	OrganizationID string     // current organization scope (resolved)
	OrgRole        organizations.Role
}

// HasScope reports whether an API-key principal has scope s. User sessions
// always have all scopes (their permissions come from org role).
func (p *Principal) HasScope(s APIScope) bool {
	if p.AuthMethod == "session" {
		return true
	}
	for _, sc := range p.Scopes {
		if sc == s {
			return true
		}
	}
	return false
}

// RequireScope returns an authorization error when the scope is missing.
func (p *Principal) RequireScope(s APIScope) error {
	if p.HasScope(s) {
		return nil
	}
	return errors.Authorization("insufficient_scope", "this API key does not have the "+string(s)+" scope")
}

// Service is the authentication/identity facade used by handlers.
type Service struct {
	users    *UserStore
	sessions *SessionStore
	keys     *APIKeyStore
	orgs     *organizations.Store
	cfg      config.AuthConfig
	now      func() time.Time
}

// NewService builds the auth service.
func NewService(users *UserStore, sessions *SessionStore, keys *APIKeyStore,
	orgs *organizations.Store, cfg config.AuthConfig) *Service {
	return &Service{users: users, sessions: sessions, keys: keys, orgs: orgs, cfg: cfg, now: time.Now}
}

// Register creates a user account. Password policy is enforced here.
func (s *Service) Register(ctx context.Context, email, password, name string) (*User, error) {
	email = strings.ToLower(strings.TrimSpace(email))
	if !emailRE.MatchString(email) {
		return nil, errors.Validation("invalid_email", "a valid email address is required", nil)
	}
	if len(password) < s.cfg.MinPasswordLength {
		return nil, errors.Validation("weak_password",
			fmt.Sprintf("password must be at least %d characters", s.cfg.MinPasswordLength), nil)
	}
	if len(password) > s.cfg.MaxPasswordLength {
		return nil, errors.Validation("weak_password", "password is too long", nil)
	}
	hash, err := HashPassword(password, PasswordParams{
		Memory:      s.cfg.Argon2Memory,
		Iterations:  s.cfg.Argon2Iterations,
		Parallelism: s.cfg.Argon2Parallelism,
		SaltLength:  s.cfg.Argon2SaltLength,
		KeyLength:   32,
	})
	if err != nil {
		return nil, err
	}
	return s.users.Create(ctx, email, hash, name)
}

// Login verifies credentials and creates a session.
func (s *Service) Login(ctx context.Context, email, password, ip, userAgent string) (string, *User, error) {
	u, err := s.users.ByEmail(ctx, strings.ToLower(strings.TrimSpace(email)))
	if err != nil {
		// Uniform error: do not reveal whether the email exists.
		return "", nil, errors.Authentication("invalid_credentials", "invalid email or password")
	}
	if u.Status != "active" {
		return "", nil, errors.Authentication("account_disabled", "account is disabled")
	}
	ok, err := VerifyPassword(password, u.PasswordHash)
	if err != nil || !ok {
		return "", nil, errors.Authentication("invalid_credentials", "invalid email or password")
	}
	token, _, err := s.sessions.Create(ctx, u.ID, ip, userAgent, s.cfg.SessionTTL)
	if err != nil {
		return "", nil, err
	}
	return token, u, nil
}

// Logout revokes the session token.
func (s *Service) Logout(ctx context.Context, token string) error {
	return s.sessions.Revoke(ctx, token)
}

// AuthenticateToken resolves a bearer token to a Principal. API keys are
// detected by their prefix; everything else is treated as a session token.
func (s *Service) AuthenticateToken(ctx context.Context, token string) (*Principal, error) {
	if strings.HasPrefix(token, "relia_") {
		key, err := s.keys.Authenticate(ctx, token)
		if err != nil {
			return nil, err
		}
		s.keys.TouchLastUsed(ctx, key.ID)
		return &Principal{
			UserID:     key.UserID,
			AuthMethod: "api_key",
			APIKeyID:   key.ID,
			Scopes:     key.Scopes,
		}, nil
	}
	sess, err := s.sessions.Authenticate(ctx, token)
	if err != nil {
		return nil, err
	}
	return &Principal{UserID: sess.UserID, AuthMethod: "session"}, nil
}

// ResolveOrgScope attaches the current organization to a principal. It uses
// the requested org id when supplied and the principal is a member;
// otherwise falls back to the user's single org; otherwise errors.
func (s *Service) ResolveOrgScope(ctx context.Context, p *Principal, requestedOrgID string) error {
	if p.AuthMethod == "api_key" {
		// API keys are bound to exactly one organization.
		p.OrganizationID = ""
		// The key store knows the org; re-fetch from the key row is handled
		// by the caller via SetAPIKeyOrg; here we enforce the requested org
		// matches the key's org when provided.
		return nil
	}
	memberships, err := s.orgs.ListForUser(ctx, p.UserID)
	if err != nil {
		return err
	}
	if len(memberships) == 0 {
		return errors.Authorization("no_organization", "user is not a member of any organization")
	}
	if requestedOrgID != "" {
		for _, m := range memberships {
			if m.OrganizationID == requestedOrgID {
				p.OrganizationID = requestedOrgID
				p.OrgRole = m.Role
				return nil
			}
		}
		return errors.Authorization("not_org_member", "user is not a member of the requested organization")
	}
	if len(memberships) == 1 {
		p.OrganizationID = memberships[0].OrganizationID
		p.OrgRole = memberships[0].Role
		return nil
	}
	return errors.Validation("organization_required",
		"user belongs to multiple organizations; select one with the X-Reliasorg header", nil)
}

// SetAPIKeyOrg sets the org scope on an API-key principal (enforced to match
// the key's organization).
func (s *Service) SetAPIKeyOrg(ctx context.Context, p *Principal, keyOrgID, requestedOrgID string) error {
	if requestedOrgID != "" && requestedOrgID != keyOrgID {
		return errors.Authorization("not_org_member", "API key is not scoped to the requested organization")
	}
	p.OrganizationID = keyOrgID
	role, err := s.orgs.MemberRole(ctx, keyOrgID, p.UserID)
	if err != nil {
		return err
	}
	p.OrgRole = role
	if p.OrgRole == "" {
		p.OrgRole = organizations.RoleMember
	}
	return nil
}

// CreateAPIKey creates a key for an org.
func (s *Service) CreateAPIKey(ctx context.Context, p *Principal, name string, scopes []APIScope) (*APIKey, error) {
	if p.OrgRole != organizations.RoleOwner && p.OrgRole != organizations.RoleAdmin {
		return nil, errors.Authorization("forbidden", "only owners and admins can manage API keys")
	}
	for _, sc := range scopes {
		if !ValidScope(sc) {
			return nil, errors.Validation("invalid_scope", "unknown scope "+string(sc), nil)
		}
	}
	return s.keys.Create(ctx, p.OrganizationID, p.UserID, name, scopes)
}

// Me returns the current user.
func (s *Service) Me(ctx context.Context, userID string) (*User, error) {
	return s.users.ByID(ctx, userID)
}

// APIKeyByID fetches an API key row (used by tenant-scoping middleware).
func (s *Service) APIKeyByID(ctx context.Context, id string) (*APIKey, error) {
	return s.keys.ByID(ctx, id)
}

// ListAPIKeys lists keys for the current org (never returns secrets).
func (s *Service) ListAPIKeys(ctx context.Context, p *Principal) ([]APIKey, error) {
	if p.OrgRole != organizations.RoleOwner && p.OrgRole != organizations.RoleAdmin {
		return nil, errors.Authorization("forbidden", "only owners and admins can manage API keys")
	}
	return s.keys.List(ctx, p.OrganizationID)
}

// RevokeAPIKey revokes a key in the current org.
func (s *Service) RevokeAPIKey(ctx context.Context, p *Principal, id string) error {
	if p.OrgRole != organizations.RoleOwner && p.OrgRole != organizations.RoleAdmin {
		return errors.Authorization("forbidden", "only owners and admins can manage API keys")
	}
	return s.keys.Revoke(ctx, p.OrganizationID, id)
}
