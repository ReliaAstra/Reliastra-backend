// Package errors defines the typed application error taxonomy used across
// Reliastra. Handlers map these to HTTP responses; infrastructure code maps
// low-level failures into them. Internal details (SQL text, stack traces,
// dependency error strings) never cross the API boundary.
package errors

import (
	"errors"
	"fmt"
	"net/http"
)

// Kind is the stable machine-readable category of an error.
type Kind string

const (
	KindValidation        Kind = "validation_error"
	KindAuthentication    Kind = "authentication_error"
	KindAuthorization     Kind = "authorization_error"
	KindNotFound          Kind = "not_found"
	KindConflict          Kind = "conflict"
	KindRateLimited       Kind = "rate_limited"
	KindUnavailable       Kind = "dependency_unavailable"
	KindInternal          Kind = "internal_error"
	KindBadRequest        Kind = "bad_request"
	KindUnprocessable     Kind = "unprocessable_entity"
)

// Error is a typed application error.
type Error struct {
	Kind      Kind
	Code      string // stable machine code, e.g. "monitor_not_found"
	Message   string // safe, human-readable message
	Details   map[string]any
	RequestID string
	cause     error
}

func (e *Error) Error() string {
	if e.cause != nil {
		return fmt.Sprintf("%s: %s: %v", e.Kind, e.Message, e.cause)
	}
	return fmt.Sprintf("%s: %s", e.Kind, e.Message)
}

func (e *Error) Unwrap() error { return e.cause }

// KindOf returns the Kind of err, defaulting to KindInternal.
func KindOf(err error) Kind {
	var e *Error
	if errors.As(err, &e) {
		return e.Kind
	}
	return KindInternal
}

// WithCause attaches a wrapped cause for logging (never rendered to clients).
func WithCause(err *Error, cause error) *Error {
	err.cause = cause
	return err
}

func new(kind Kind, code, message string) *Error {
	return &Error{Kind: kind, Code: code, Message: message}
}

// Validation creates a validation error with optional field details.
func Validation(code, message string, details map[string]any) *Error {
	return &Error{Kind: KindValidation, Code: code, Message: message, Details: details}
}

// Authentication creates an authentication error.
func Authentication(code, message string) *Error { return new(KindAuthentication, code, message) }

// Authorization creates an authorization error.
func Authorization(code, message string) *Error { return new(KindAuthorization, code, message) }

// NotFound creates a not-found error.
func NotFound(code, message string) *Error { return new(KindNotFound, code, message) }

// Conflict creates a conflict error.
func Conflict(code, message string) *Error { return new(KindConflict, code, message) }

// RateLimited creates a rate-limit error. RetryAfter seconds may be included.
func RateLimited(code, message string, retryAfter int) *Error {
	e := new(KindRateLimited, code, message)
	if retryAfter > 0 {
		e.Details = map[string]any{"retry_after": retryAfter}
	}
	return e
}

// Unavailable creates a dependency-unavailable error.
func Unavailable(code, message string) *Error { return new(KindUnavailable, code, message) }

// Internal creates an internal error. The message must be safe to expose.
func Internal(code, message string) *Error { return new(KindInternal, code, message) }

// BadRequest creates a 400 error.
func BadRequest(code, message string) *Error { return new(KindBadRequest, code, message) }

// Unprocessable creates a 422 error.
func Unprocessable(code, message string, details map[string]any) *Error {
	return &Error{Kind: KindUnprocessable, Code: code, Message: message, Details: details}
}

// HTTPStatus maps a Kind to its HTTP status code.
func HTTPStatus(kind Kind) int {
	switch kind {
	case KindValidation, KindBadRequest:
		return http.StatusBadRequest
	case KindAuthentication:
		return http.StatusUnauthorized
	case KindAuthorization:
		return http.StatusForbidden
	case KindNotFound:
		return http.StatusNotFound
	case KindConflict:
		return http.StatusConflict
	case KindRateLimited:
		return http.StatusTooManyRequests
	case KindUnavailable:
		return http.StatusServiceUnavailable
	case KindUnprocessable:
		return http.StatusUnprocessableEntity
	default:
		return http.StatusInternalServerError
	}
}
