package organizations

import "context"

// PlanForOrg returns the effective plan slug for an organization.
func (s *Store) PlanForOrg(ctx context.Context, orgID string) (string, error) {
	var plan string
	err := s.pool.QueryRow(ctx, `SELECT plan FROM organizations WHERE id=$1`, orgID).Scan(&plan)
	if err != nil {
		return "", err
	}
	return plan, nil
}
