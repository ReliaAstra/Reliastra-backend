// Package dependencies models external dependencies a customer service relies
// on. No vendor-specific business logic lives here; vendors are data.
package dependencies

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Dependency is an external system.
type Dependency struct {
	ID         string            `json:"id"`
	ProjectID  string            `json:"project_id"`
	Name       string            `json:"name"`
	Provider   string            `json:"provider"`
	Type       string            `json:"type"`
	Identifier string            `json:"identifier"`
	Metadata   map[string]any    `json:"metadata"`
	CreatedAt  time.Time         `json:"created_at"`
	UpdatedAt  time.Time         `json:"updated_at"`
}

// ValidTypes are the supported dependency types (extensible list).
var ValidTypes = []string{"api", "cloud", "cdn", "auth", "payment", "email", "ai", "database", "dns", "other"}

// ValidType reports whether t is a supported type.
func ValidType(t string) bool {
	for _, v := range ValidTypes {
		if v == t {
			return true
		}
	}
	return false
}

// ServiceDependency is the service -> dependency relationship with criticality.
type ServiceDependency struct {
	ID           string    `json:"id"`
	ServiceID    string    `json:"service_id"`
	DependencyID string    `json:"dependency_id"`
	Criticality  string    `json:"criticality"`
	Description  string    `json:"description"`
	CreatedAt    time.Time `json:"created_at"`
}

// ValidCriticalities are the supported criticality values.
var ValidCriticalities = []string{"low", "medium", "high", "critical"}

// ValidCriticality reports whether c is supported.
func ValidCriticality(c string) bool {
	for _, v := range ValidCriticalities {
		if v == c {
			return true
		}
	}
	return false
}

// Store persists dependencies and relationships.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const cols = `id, project_id, name, provider, type, identifier, metadata, created_at, updated_at`

func (s *Store) projectOwned(ctx context.Context, orgID, projectID string) error {
	var one int
	err := s.pool.QueryRow(ctx, `SELECT 1 FROM projects WHERE id=$1 AND organization_id=$2`,
		projectID, orgID).Scan(&one)
	if err == pgx.ErrNoRows {
		return errors.NotFound("project_not_found", "project not found in this organization")
	}
	return err
}

// Create inserts a dependency.
func (s *Store) Create(ctx context.Context, orgID, projectID, name, provider, typ, identifier string, metadata map[string]any) (*Dependency, error) {
	if err := s.projectOwned(ctx, orgID, projectID); err != nil {
		return nil, err
	}
	if !ValidType(typ) {
		return nil, errors.Validation("invalid_type", "unsupported dependency type", map[string]any{"allowed": ValidTypes})
	}
	if metadata == nil {
		metadata = map[string]any{}
	}
	metaJSON, err := json.Marshal(metadata)
	if err != nil {
		return nil, err
	}
	d := &Dependency{
		ID: ids.NewUUID(), ProjectID: projectID, Name: name, Provider: provider,
		Type: typ, Identifier: identifier, Metadata: metadata,
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO dependencies (id, project_id, name, provider, type, identifier, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`, d.ID, d.ProjectID, d.Name, d.Provider, d.Type, d.Identifier, string(metaJSON))
	if err != nil {
		if isUniqueViolation(err) {
			return nil, errors.Conflict("name_taken", "a dependency with this name already exists in the project")
		}
		return nil, err
	}
	return d, nil
}

// ByID returns a dependency validated through org -> project ownership.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*Dependency, error) {
	row := s.pool.QueryRow(ctx, `
		SELECT d.id, d.project_id, d.name, d.provider, d.type, d.identifier, d.metadata, d.created_at, d.updated_at
		FROM dependencies d JOIN projects p ON p.id = d.project_id
		WHERE d.id=$1 AND p.organization_id=$2`, id, orgID)
	var d Dependency
	var metaJSON []byte
	err := row.Scan(&d.ID, &d.ProjectID, &d.Name, &d.Provider, &d.Type, &d.Identifier,
		&metaJSON, &d.CreatedAt, &d.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("dependency_not_found", "dependency not found")
	}
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(metaJSON, &d.Metadata)
	return &d, nil
}

// List returns dependencies in an org, optionally filtered by project.
func (s *Store) List(ctx context.Context, orgID, projectID string) ([]Dependency, error) {
	query := `SELECT d.id, d.project_id, d.name, d.provider, d.type, d.identifier, d.metadata, d.created_at, d.updated_at
		FROM dependencies d JOIN projects p ON p.id = d.project_id
		WHERE p.organization_id = $1`
	args := []any{orgID}
	if projectID != "" {
		query += ` AND d.project_id = $2`
		args = append(args, projectID)
	}
	query += ` ORDER BY d.created_at`
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Dependency
	for rows.Next() {
		var d Dependency
		var metaJSON []byte
		if err := rows.Scan(&d.ID, &d.ProjectID, &d.Name, &d.Provider, &d.Type, &d.Identifier,
			&metaJSON, &d.CreatedAt, &d.UpdatedAt); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(metaJSON, &d.Metadata)
		out = append(out, d)
	}
	return out, rows.Err()
}

// Delete removes a dependency.
func (s *Store) Delete(ctx context.Context, orgID, id string) error {
	_, err := s.ByID(ctx, orgID, id)
	if err != nil {
		return err
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM dependencies WHERE id=$1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("dependency_not_found", "dependency not found")
	}
	return nil
}

// ListForService returns the dependencies linked to a service, with
// criticality (org-scoped).
func (s *Store) ListForService(ctx context.Context, orgID, serviceID string) ([]ServiceDependency, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT sd.id, sd.service_id, sd.dependency_id, sd.criticality, sd.description, sd.created_at
		FROM service_dependencies sd
		JOIN services sv ON sv.id = sd.service_id
		JOIN projects p ON p.id = sv.project_id
		WHERE sd.service_id=$1 AND p.organization_id=$2
		ORDER BY sd.created_at`, serviceID, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ServiceDependency
	for rows.Next() {
		var sd ServiceDependency
		if err := rows.Scan(&sd.ID, &sd.ServiceID, &sd.DependencyID, &sd.Criticality,
			&sd.Description, &sd.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, sd)
	}
	return out, rows.Err()
}

// Link associates a dependency with a service (org-scoped).
func (s *Store) Link(ctx context.Context, orgID, serviceID, dependencyID, criticality, description string) (*ServiceDependency, error) {
	// Validate both entities belong to the org.
	if _, err := s.ByID(ctx, orgID, dependencyID); err != nil {
		return nil, err
	}
	// Validate the service belongs to the org.
	var one int
	err := s.pool.QueryRow(ctx, `
		SELECT 1 FROM services sv JOIN projects p ON p.id = sv.project_id
		WHERE sv.id=$1 AND p.organization_id=$2`, serviceID, orgID).Scan(&one)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("service_not_found", "service not found")
	}
	if err != nil {
		return nil, err
	}
	if !ValidCriticality(criticality) {
		return nil, errors.Validation("invalid_criticality", "criticality must be low, medium, high or critical", nil)
	}
	sd := &ServiceDependency{
		ID: ids.NewUUID(), ServiceID: serviceID, DependencyID: dependencyID,
		Criticality: criticality, Description: description,
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO service_dependencies (id, service_id, dependency_id, criticality, description)
		VALUES ($1,$2,$3,$4,$5)`, sd.ID, sd.ServiceID, sd.DependencyID, sd.Criticality, sd.Description)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, errors.Conflict("already_linked", "this dependency is already linked to the service")
		}
		return nil, err
	}
	return sd, nil
}

// Unlink removes the association.
func (s *Store) Unlink(ctx context.Context, orgID, serviceID, dependencyID string) error {
	tag, err := s.pool.Exec(ctx, `
		DELETE FROM service_dependencies sd
		USING services sv, projects p
		WHERE sd.service_id = sv.id AND sv.project_id = p.id
		  AND sd.service_id=$1 AND sd.dependency_id=$2 AND p.organization_id=$3`,
		serviceID, dependencyID, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("link_not_found", "service-dependency link not found")
	}
	return nil
}

// LinkedDependency is a dependency with its relationship criticality,
// returned to correlation.
type LinkedDependency struct {
	Dependency
	Criticality string
}

// LinkedForService fetches full dependency rows linked to a service.
func (s *Store) LinkedForService(ctx context.Context, serviceID string) ([]LinkedDependency, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT d.id, d.project_id, d.name, d.provider, d.type, d.identifier, d.metadata,
		       d.created_at, d.updated_at, sd.criticality
		FROM service_dependencies sd
		JOIN dependencies d ON d.id = sd.dependency_id
		WHERE sd.service_id = $1`, serviceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []LinkedDependency
	for rows.Next() {
		var ld LinkedDependency
		var metaJSON []byte
		if err := rows.Scan(&ld.ID, &ld.ProjectID, &ld.Name, &ld.Provider, &ld.Type, &ld.Identifier,
			&metaJSON, &ld.CreatedAt, &ld.UpdatedAt, &ld.Criticality); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(metaJSON, &ld.Metadata)
		out = append(out, ld)
	}
	return out, rows.Err()
}
