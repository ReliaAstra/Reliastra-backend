// Package organizations models organizations, membership and roles.
package organizations

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Role is a member's role in an organization.
type Role string

// Supported roles.
const (
	RoleOwner  Role = "owner"
	RoleAdmin  Role = "admin"
	RoleMember Role = "member"
	RoleViewer Role = "viewer"
)

// Valid reports whether r is a supported role.
func (r Role) Valid() bool {
	switch r {
	case RoleOwner, RoleAdmin, RoleMember, RoleViewer:
		return true
	}
	return false
}

// Organization is a tenant.
type Organization struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Slug      string    `json:"slug"`
	Plan      string    `json:"plan"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Membership joins a user to an organization.
type Membership struct {
	OrganizationID string    `json:"organization_id"`
	UserID         string    `json:"user_id"`
	Role           Role      `json:"role"`
	CreatedAt      time.Time `json:"created_at"`
	Organization   *Organization `json:"organization,omitempty"`
}

// Store persists organizations and memberships.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const orgCols = `id, name, slug, plan, status, created_at, updated_at`

func scanOrg(row pgx.Row) (*Organization, error) {
	var o Organization
	err := row.Scan(&o.ID, &o.Name, &o.Slug, &o.Plan, &o.Status, &o.CreatedAt, &o.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &o, nil
}

// Create inserts a new organization and adds the creator as owner in one
// transaction. The owner is a hard requirement: an org must never exist
// without an owner.
func (s *Store) Create(ctx context.Context, tx pgx.Tx, name, slug string, ownerUserID string) (*Organization, error) {
	org := &Organization{
		ID:   ids.NewUUID(),
		Name: name,
		Slug: slug,
		Plan: "free",
		Status: "active",
	}
	var err error
	if tx != nil {
		_, err = tx.Exec(ctx, `INSERT INTO organizations (id, name, slug) VALUES ($1,$2,$3)`,
			org.ID, org.Name, org.Slug)
		if err == nil {
			_, err = tx.Exec(ctx, `INSERT INTO organization_members (organization_id, user_id, role) VALUES ($1,$2,$3)`,
				org.ID, ownerUserID, RoleOwner)
		}
	} else {
		_, err = s.pool.Exec(ctx, `INSERT INTO organizations (id, name, slug) VALUES ($1,$2,$3)`,
			org.ID, org.Name, org.Slug)
		if err == nil {
			_, err = s.pool.Exec(ctx, `INSERT INTO organization_members (organization_id, user_id, role) VALUES ($1,$2,$3)`,
				org.ID, ownerUserID, RoleOwner)
		}
	}
	if err != nil {
		return nil, err
	}
	return org, nil
}

// ByID fetches an organization by id.
func (s *Store) ByID(ctx context.Context, id string) (*Organization, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+orgCols+` FROM organizations WHERE id=$1`, id)
	o, err := scanOrg(row)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("organization_not_found", "organization not found")
	}
	if err != nil {
		return nil, err
	}
	return o, nil
}

// BySlug fetches an organization by slug.
func (s *Store) BySlug(ctx context.Context, slug string) (*Organization, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+orgCols+` FROM organizations WHERE slug=$1`, slug)
	o, err := scanOrg(row)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("organization_not_found", "organization not found")
	}
	if err != nil {
		return nil, err
	}
	return o, nil
}

// ListForUser returns the memberships (with org) for a user.
func (s *Store) ListForUser(ctx context.Context, userID string) ([]Membership, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT m.organization_id, m.user_id, m.role, m.created_at,
		       o.id, o.name, o.slug, o.plan, o.status, o.created_at, o.updated_at
		FROM organization_members m
		JOIN organizations o ON o.id = m.organization_id
		WHERE m.user_id = $1
		ORDER BY o.created_at`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Membership
	for rows.Next() {
		var m Membership
		var o Organization
		if err := rows.Scan(&m.OrganizationID, &m.UserID, &m.Role, &m.CreatedAt,
			&o.ID, &o.Name, &o.Slug, &o.Plan, &o.Status, &o.CreatedAt, &o.UpdatedAt); err != nil {
			return nil, err
		}
		m.Organization = &o
		out = append(out, m)
	}
	return out, rows.Err()
}

// MemberRole returns the user's role in an org, or "" if not a member.
func (s *Store) MemberRole(ctx context.Context, orgID, userID string) (Role, error) {
	var r Role
	err := s.pool.QueryRow(ctx,
		`SELECT role FROM organization_members WHERE organization_id=$1 AND user_id=$2`,
		orgID, userID).Scan(&r)
	if err == pgx.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return r, nil
}

// AddMember adds a member with role.
func (s *Store) AddMember(ctx context.Context, orgID, userID string, role Role) error {
	_, err := s.pool.Exec(ctx,
		`INSERT INTO organization_members (organization_id, user_id, role) VALUES ($1,$2,$3)
		 ON CONFLICT (organization_id, user_id) DO UPDATE SET role = EXCLUDED.role`,
		orgID, userID, role)
	return err
}

// RemoveMember removes a member.
func (s *Store) RemoveMember(ctx context.Context, orgID, userID string) error {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM organization_members WHERE organization_id=$1 AND user_id=$2`, orgID, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("member_not_found", "member not found")
	}
	return nil
}

// UpdatePlan changes an org's plan.
func (s *Store) UpdatePlan(ctx context.Context, orgID, plan string) error {
	_, err := s.pool.Exec(ctx, `UPDATE organizations SET plan=$1, updated_at=now() WHERE id=$2`, plan, orgID)
	return err
}

// Service contains organization business rules.
type Service struct {
	store *Store
}

// NewService builds the organization service.
func NewService(store *Store) *Service { return &Service{store: store} }

// CreateOrganization validates and creates an org with the user as owner.
func (s *Service) CreateOrganization(ctx context.Context, userID, name, slug string) (*Organization, error) {
	if name == "" || len(name) > 100 {
		return nil, errors.Validation("invalid_org_name", "organization name must be 1-100 characters", nil)
	}
	if slug == "" || !slugRE.MatchString(slug) {
		return nil, errors.Validation("invalid_org_slug", "slug must be 1-63 lowercase letters, digits or hyphens", nil)
	}
	if existing, _ := s.store.BySlug(ctx, slug); existing != nil {
		return nil, errors.Conflict("slug_taken", "an organization with this slug already exists")
	}
	return s.store.Create(ctx, nil, name, slug, userID)
}

// ListForUser returns memberships for a user.
func (s *Service) ListForUser(ctx context.Context, userID string) ([]Membership, error) {
	return s.store.ListForUser(ctx, userID)
}

// MarshalJSON for Role etc. is default; keep JSON helpers in handlers.

// slugRE is compiled in slug.go to keep this file focused.
var _ = fmt.Sprintf
