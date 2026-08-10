// Package httpapi provides the HTTP server plumbing: response envelope,
// middleware (request id, logging, recovery, security headers, CORS, body
// limits, rate limiting, authentication, tenant scoping) and routing helpers.
package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

// Envelope is the uniform API response wrapper.
type Envelope struct {
	Data      any            `json:"data,omitempty"`
	Error     *ErrorBody     `json:"error,omitempty"`
	RequestID string         `json:"request_id,omitempty"`
	Meta      map[string]any `json:"meta,omitempty"`
}

// ErrorBody is the machine-readable error shape.
type ErrorBody struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	RequestID string `json:"request_id,omitempty"`
	Details   any    `json:"details,omitempty"`
}

// WriteJSON writes a JSON response with the given status code.
func WriteJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// WriteData writes a success envelope.
func WriteData(w http.ResponseWriter, requestID string, status int, data any) {
	WriteJSON(w, status, Envelope{Data: data, RequestID: requestID})
}

// WriteError writes an error envelope mapped from a typed error.
func WriteError(w http.ResponseWriter, logger *slog.Logger, requestID string, err error) {
	appErr, ok := err.(*errors.Error)
	if !ok {
		appErr = errors.Internal("internal_error", "an unexpected error occurred")
	}
	status := errors.HTTPStatus(appErr.Kind)
	if appErr.Kind == errors.KindInternal {
		logger.Error("internal error", "error", err.Error(), "request_id", requestID)
	}
	body := &ErrorBody{
		Code:      appErr.Code,
		Message:   appErr.Message,
		RequestID: requestID,
		Details:   appErr.Details,
	}
	WriteJSON(w, status, Envelope{Error: body, RequestID: requestID})
}

// DecodeJSON reads and validates the JSON body, enforcing the body limit.
func DecodeJSON(w http.ResponseWriter, r *http.Request, dst any, requestID string) error {
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // bounded by middleware too
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return errors.Validation("invalid_json", "request body is not valid JSON: "+err.Error(), nil)
	}
	return nil
}
