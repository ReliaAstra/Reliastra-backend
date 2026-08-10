// Package logging provides structured JSON logging built on log/slog.
//
// Every log line carries: timestamp, level, service, component, message and
// any context fields. Request-scoped fields (request_id, trace_id) are
// propagated through the context via WithContext/FromContext. Secret values
// are never logged; use Redact to sanitize before logging.
package logging

import (
	"context"
	"io"
	"log/slog"
	"os"
)

type ctxKey struct{}

type contextFields struct {
	requestID   string
	traceID     string
	spanID      string
	orgID       string
	projectID   string
	userID      string
	actorType   string
	extra       map[string]any
}

// New creates a JSON slog.Logger writing to w. level is one of
// debug, info, warn, error.
func New(w io.Writer, level string, service string) *slog.Logger {
	var lvl slog.Level
	switch level {
	case "debug":
		lvl = slog.LevelDebug
	case "warn":
		lvl = slog.LevelWarn
	case "error":
		lvl = slog.LevelError
	default:
		lvl = slog.LevelInfo
	}
	h := slog.NewJSONHandler(w, &slog.HandlerOptions{Level: lvl})
	return slog.New(h).With("service", service)
}

// NewDefault builds a logger writing to stdout at INFO level.
func NewDefault(service string) *slog.Logger {
	return New(os.Stdout, "info", service)
}

// WithRequest returns a context carrying request-scoped log fields.
func WithRequest(ctx context.Context, requestID, traceID, spanID string) context.Context {
	f := from(ctx)
	f.requestID, f.traceID, f.spanID = requestID, traceID, spanID
	return context.WithValue(ctx, ctxKey{}, f)
}

// WithActor attaches the acting principal (user id, org id).
func WithActor(ctx context.Context, userID, orgID string) context.Context {
	f := from(ctx)
	f.userID, f.orgID = userID, orgID
	return context.WithValue(ctx, ctxKey{}, f)
}

// WithOrg attaches an organization id.
func WithOrg(ctx context.Context, orgID string) context.Context {
	f := from(ctx)
	f.orgID = orgID
	return context.WithValue(ctx, ctxKey{}, f)
}

// WithContext returns a logger enriched with request-scoped fields.
func WithContext(logger *slog.Logger, ctx context.Context) *slog.Logger {
	f := from(ctx)
	if f.requestID != "" {
		logger = logger.With("request_id", f.requestID)
	}
	if f.traceID != "" {
		logger = logger.With("trace_id", f.traceID)
	}
	if f.spanID != "" {
		logger = logger.With("span_id", f.spanID)
	}
	if f.orgID != "" {
		logger = logger.With("organization_id", f.orgID)
	}
	if f.userID != "" {
		logger = logger.With("actor_id", f.userID)
	}
	for k, v := range f.extra {
		logger = logger.With(k, v)
	}
	return logger
}

// FromContext extracts a fresh context-fields struct.
func from(ctx context.Context) *contextFields {
	if f, ok := ctx.Value(ctxKey{}).(*contextFields); ok {
		// copy-on-write so callers never mutate shared state
		cp := *f
		if f.extra != nil {
			cp.extra = make(map[string]any, len(f.extra))
			for k, v := range f.extra {
				cp.extra[k] = v
			}
		}
		return &cp
	}
	return &contextFields{}
}

// Redact returns "***" for any value that should never be logged.
func Redact() string { return "***" }

// SecretList are field names that are automatically redacted by RedactMap.
var SecretList = []string{
	"authorization", "cookie", "x-api-key", "password", "password_hash",
	"api_key", "api_key_secret", "token", "access_token", "refresh_token",
	"secret", "client_secret", "webhook_secret", "body",
}

// RedactMap returns a copy of m with known secret fields redacted.
func RedactMap(m map[string]any) map[string]any {
	out := make(map[string]any, len(m))
	for k, v := range m {
		if isSecretKey(k) {
			out[k] = Redact()
		} else {
			out[k] = v
		}
	}
	return out
}

func isSecretKey(k string) bool {
	lk := k
	for _, s := range SecretList {
		if lk == s {
			return true
		}
	}
	return false
}
