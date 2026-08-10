package auth

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// APIScope is a permission scope for API keys.
type APIScope string

// Supported API key scopes.
const (
	ScopeMonitorRead    APIScope = "monitor:read"
	ScopeMonitorWrite   APIScope = "monitor:write"
	ScopeIncidentRead   APIScope = "incident:read"
	ScopeEvidenceRead   APIScope = "evidence:read"
	ScopeEvidenceWrite  APIScope = "evidence:write"
	ScopeProjectAdmin   APIScope = "project:admin"
	ScopeCheckResultRead APIScope = "check_result:read"
)

// ValidScope reports whether s is a known scope.
func ValidScope(s APIScope) bool {
	switch s {
	case ScopeMonitorRead, ScopeMonitorWrite, ScopeIncidentRead,
		ScopeEvidenceRead, ScopeEvidenceWrite, ScopeProjectAdmin, ScopeCheckResultRead:
		return true
	}
	return false
}

// APIKey is a programmatic credential. Secret is only present at creation.
type APIKey struct {
	ID             string     `json:"id"`
	OrganizationID string     `json:"organization_id"`
	UserID         string     `json:"user_id"`
	Name           string     `json:"name"`
	Prefix         string     `json:"prefix"`
	Scopes         []APIScope `json:"scopes"`
	Status         string     `json:"status"`
	Secret         string     `json:"secret,omitempty"`
	LastUsedAt     *time.Time `json:"last_used_at,omitempty"`
	CreatedAt      time.Time  `json:"created_at"`
}

// APIKeyStore persists API keys.
type APIKeyStore struct {
	pool *pgxpool.Pool
}

// NewAPIKeyStore builds an APIKeyStore.
func NewAPIKeyStore(pool *pgxpool.Pool) *APIKeyStore { return &APIKeyStore{pool: pool} }

// Create generates a key, storing only its hash. The plaintext secret is
// returned exactly once.
func (s *APIKeyStore) Create(ctx context.Context, orgID, userID, name string, scopes []APIScope) (*APIKey, error) {
	secret := ids.NewAPIKey()
	prefix := secret[:min(12, len(secret))]
	scopeJSON, err := json.Marshal(scopes)
	if err != nil {
		return nil, err
	}
	key := &APIKey{
		ID:             ids.NewUUID(),
		OrganizationID: orgID,
		UserID:         userID,
		Name:           name,
		Prefix:         prefix,
		Scopes:         scopes,
		Status:         "active",
		Secret:         secret,
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO api_keys (id, organization_id, user_id, name, key_hash, prefix, scopes)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		key.ID, key.OrganizationID, key.UserID, key.Name, HashToken(secret), key.Prefix, scopeJSON)
	if err != nil {
		return nil, err
	}
	return key, nil
}

// Authenticate validates a raw key secret and returns the key with scopes.
func (s *APIKeyStore) Authenticate(ctx context.Context, secret string) (*APIKey, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, organization_id, user_id, name, prefix, scopes, status, created_at
		FROM api_keys WHERE key_hash = $1`, HashToken(secret))
	var key APIKey
	var scopesJSON []byte
	err := row.Scan(&key.ID, &key.OrganizationID, &key.UserID, &key.Name, &key.Prefix,
		&scopesJSON, &key.Status, &key.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.Authentication("invalid_api_key", "invalid API key")
	}
	if err != nil {
		return nil, err
	}
	if key.Status != "active" {
		return nil, errors.Authentication("revoked_api_key", "API key is revoked")
	}
	if err := json.Unmarshal(scopesJSON, &key.Scopes); err != nil {
		return nil, err
	}
	return &key, nil
}

// TouchLastUsed updates the last_used_at timestamp (best effort).
func (s *APIKeyStore) TouchLastUsed(ctx context.Context, id string) {
	_, _ = s.pool.Exec(ctx, `UPDATE api_keys SET last_used_at = now() WHERE id = $1`, id)
}

// ByID fetches a key (including for API-key authenticated principals).
func (s *APIKeyStore) ByID(ctx context.Context, id string) (*APIKey, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, organization_id, user_id, name, prefix, scopes, status, created_at
		FROM api_keys WHERE id = $1`, id)
	var key APIKey
	var scopesJSON []byte
	err := row.Scan(&key.ID, &key.OrganizationID, &key.UserID, &key.Name, &key.Prefix,
		&scopesJSON, &key.Status, &key.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("api_key_not_found", "API key not found")
	}
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(scopesJSON, &key.Scopes)
	return &key, nil
}

// Revoke marks a key revoked.
func (s *APIKeyStore) Revoke(ctx context.Context, orgID, id string) error {
	tag, err := s.pool.Exec(ctx, `UPDATE api_keys SET status='revoked', revoked_at=now()
		WHERE id=$1 AND organization_id=$2 AND status='active'`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("api_key_not_found", "API key not found")
	}
	return nil
}

// List returns active keys for an org (never includes secrets).
func (s *APIKeyStore) List(ctx context.Context, orgID string) ([]APIKey, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, organization_id, user_id, name, prefix, scopes, status, created_at
		FROM api_keys WHERE organization_id=$1 AND status='active' ORDER BY created_at`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []APIKey
	for rows.Next() {
		var key APIKey
		var scopesJSON []byte
		if err := rows.Scan(&key.ID, &key.OrganizationID, &key.UserID, &key.Name, &key.Prefix,
			&scopesJSON, &key.Status, &key.CreatedAt); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(scopesJSON, &key.Scopes)
		out = append(out, key)
	}
	return out, rows.Err()
}

// ParseBearer extracts the token from an Authorization header.
func ParseBearer(authz string) string {
	if len(authz) > 7 && strings.EqualFold(authz[:7], "bearer ") {
		return strings.TrimSpace(authz[7:])
	}
	return ""
}
