package api

import "github.com/ReliaAstra/reliastra-backend/pkg/errors"

// validationErr is a shorthand for field-level validation errors.
func validationErr(field, message string) error {
	return errors.Validation("invalid_"+field, message, map[string]any{field: message})
}
