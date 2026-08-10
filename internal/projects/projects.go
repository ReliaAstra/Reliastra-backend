// Package projects models tenant projects.
package projects

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Project is a tenant project.
type Project struct {
	ID             string    `json:"id"`
	OrganizationID string    `json:"organization_id"`
	Name           string    `json:"name"`
	Slug           string    `json:"slug"`
	Description    string    `json:"description"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

// Store persists projects.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const cols = `id, organization_id, name, slug, description, created_at, updated_at`

func scan(row pgx.Row) (*Project, error) {
	var p Project
	err := row.Scan(&p.ID, &p.OrganizationID, &p.Name, &p.Slug, &p.Description, &p.CreatedAt, &p.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("project_not_found", "project not found")
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// Create inserts a project.
func (s *Store) Create(ctx context.Context, orgID, name, slug, description string) (*Project, error) {
	p := &Project{ID: ids.NewUUID(), OrganizationID: orgID, Name: name, Slug: slug, Description: description}
	_, err := s.pool.Exec(ctx, `INSERT INTO projects (id, organization_id, name, slug, description)
		VALUES ($1,$2,$3,$4,$5)`, p.ID, p.OrganizationID, p.Name, p.Slug, p.Description)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, errors.Conflict("slug_taken", "a project with this slug already exists in the organization")
		}
		return nil, err
	}
	return p, nil
}

// ByID returns a project if it belongs to orgID.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*Project, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM projects WHERE id=$1 AND organization_id=$2`, id, orgID)
	return scan(row)
}

// List returns all projects for an org.
func (s *Store) List(ctx context.Context, orgID string) ([]Project, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+cols+` FROM projects WHERE organization_id=$1 ORDER BY created_at`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Project
	for rows.Next() {
		var p Project
		if err := rows.Scan(&p.ID, &p.OrganizationID, &p.Name, &p.Slug, &p.Description, &p.CreatedAt, &p.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

// Update patches name/slug/description.
func (s *Store) Update(ctx context.Context, orgID, id, name, slug, description string) (*Project, error) {
	p, err := s.ByID(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	if name != "" {
		p.Name = name
	}
	if slug != "" {
		p.Slug = slug
	}
	p.Description = description
	_, err = s.pool.Exec(ctx, `UPDATE projects SET name=$1, slug=$2, description=$3, updated_at=now()
		WHERE id=$4 AND organization_id=$5`, p.Name, p.Slug, p.Description, p.ID, p.OrganizationID)
	if err != nil {
		return nil, err
	}
	return p, nil
}

// Delete removes a project (cascades to services, dependencies, monitors,
// incidents).
func (s *Store) Delete(ctx context.Context, orgID, id string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM projects WHERE id=$1 AND organization_id=$2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("project_not_found", "project not found")
	}
	return nil
}
