// Package services models customer-owned services.
package services

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Service is a customer-owned service within a project.
type Service struct {
	ID        string    `json:"id"`
	ProjectID string    `json:"project_id"`
	Name      string    `json:"name"`
	Identifier string   `json:"identifier"`
	BaseURL   string    `json:"base_url"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Store persists services with tenant validation through project ownership.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const cols = `id, project_id, name, identifier, base_url, status, created_at, updated_at`

// projectOwned ensures the project belongs to orgID. Returns project id.
func (s *Store) projectOwned(ctx context.Context, orgID, projectID string) error {
	var one int
	err := s.pool.QueryRow(ctx, `SELECT 1 FROM projects WHERE id=$1 AND organization_id=$2`,
		projectID, orgID).Scan(&one)
	if err == pgx.ErrNoRows {
		return errors.NotFound("project_not_found", "project not found in this organization")
	}
	return err
}

// Create inserts a service in a project owned by orgID.
func (s *Store) Create(ctx context.Context, orgID, projectID, name, identifier, baseURL string) (*Service, error) {
	if err := s.projectOwned(ctx, orgID, projectID); err != nil {
		return nil, err
	}
	svc := &Service{
		ID: ids.NewUUID(), ProjectID: projectID, Name: name,
		Identifier: identifier, BaseURL: baseURL, Status: "active",
	}
	_, err := s.pool.Exec(ctx, `INSERT INTO services (id, project_id, name, identifier, base_url)
		VALUES ($1,$2,$3,$4,$5)`, svc.ID, svc.ProjectID, svc.Name, svc.Identifier, svc.BaseURL)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, errors.Conflict("identifier_taken", "a service with this identifier already exists in the project")
		}
		return nil, err
	}
	return svc, nil
}

// ByID returns a service validated through org -> project ownership.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*Service, error) {
	row := s.pool.QueryRow(ctx, `
		SELECT sv.id, sv.project_id, sv.name, sv.identifier, sv.base_url, sv.status, sv.created_at, sv.updated_at
		FROM services sv JOIN projects p ON p.id = sv.project_id
		WHERE sv.id=$1 AND p.organization_id=$2`, id, orgID)
	var svc Service
	err := row.Scan(&svc.ID, &svc.ProjectID, &svc.Name, &svc.Identifier, &svc.BaseURL,
		&svc.Status, &svc.CreatedAt, &svc.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("service_not_found", "service not found")
	}
	if err != nil {
		return nil, err
	}
	return &svc, nil
}

// List returns services in an org, optionally filtered by project.
func (s *Store) List(ctx context.Context, orgID, projectID string) ([]Service, error) {
	query := `SELECT sv.id, sv.project_id, sv.name, sv.identifier, sv.base_url, sv.status, sv.created_at, sv.updated_at
		FROM services sv JOIN projects p ON p.id = sv.project_id
		WHERE p.organization_id = $1`
	args := []any{orgID}
	if projectID != "" {
		query += ` AND sv.project_id = $2`
		args = append(args, projectID)
	}
	query += ` ORDER BY sv.created_at`
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Service
	for rows.Next() {
		var svc Service
		if err := rows.Scan(&svc.ID, &svc.ProjectID, &svc.Name, &svc.Identifier, &svc.BaseURL,
			&svc.Status, &svc.CreatedAt, &svc.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, svc)
	}
	return out, rows.Err()
}

// Update patches a service.
func (s *Store) Update(ctx context.Context, orgID, id, name, identifier, baseURL, status string) (*Service, error) {
	svc, err := s.ByID(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	if name != "" {
		svc.Name = name
	}
	if identifier != "" {
		svc.Identifier = identifier
	}
	if baseURL != "" || status != "" {
		svc.BaseURL = baseURL
	}
	if status != "" {
		if status != "active" && status != "inactive" {
			return nil, errors.Validation("invalid_status", "status must be active or inactive", nil)
		}
		svc.Status = status
	}
	_, err = s.pool.Exec(ctx, `UPDATE services SET name=$1, identifier=$2, base_url=$3, status=$4, updated_at=now()
		WHERE id=$5`, svc.Name, svc.Identifier, svc.BaseURL, svc.Status, svc.ID)
	if err != nil {
		return nil, err
	}
	return svc, nil
}

// Delete removes a service (cascades relationships and monitors).
func (s *Store) Delete(ctx context.Context, orgID, id string) error {
	_, err := s.ByID(ctx, orgID, id)
	if err != nil {
		return err
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM services WHERE id=$1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("service_not_found", "service not found")
	}
	return nil
}
