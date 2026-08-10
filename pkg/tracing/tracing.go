// Package tracing provides trace context propagation for Reliastra.
//
// Phase 1 ships a no-op / log-emitting tracer so that every code path carries
// trace context and logs correlate by trace_id, without a heavyweight SDK or
// an exporter dependency. The Tracer interface is the seam for OpenTelemetry:
// swapping the Noop tracer for an OTel-backed implementation (see
// docs/architecture/observability.md) requires no changes in callers.
package tracing

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
)

type traceKey struct{}

// Span is a unit of work within a trace. Call End when the work completes.
type Span interface {
	// End marks the span complete and records duration/error.
	End()
	// AddEvent records a timestamped event on the span.
	AddEvent(name string, attrs map[string]string)
	// SetError records that the span failed (message is safe to log).
	SetError(message string)
	// Context returns the context carrying this span.
	Context() context.Context
}

// Tracer creates spans. Implementations may be no-op, log-based, or OTel.
type Tracer interface {
	// Start begins a child span of the span in ctx (if any).
	Start(ctx context.Context, name string) (context.Context, Span)
	// TraceID returns the trace id in ctx, or "" if none.
	TraceID(ctx context.Context) string
	// SpanID returns the current span id in ctx, or "" if none.
	SpanID(ctx context.Context) string
}

// Noop is the default tracer. It still allocates real trace/span ids so
// logs remain correlatable.
type Noop struct{ Logger *slog.Logger }

// Start implements Tracer.
func (t *Noop) Start(ctx context.Context, name string) (context.Context, Span) {
	traceID := t.TraceID(ctx)
	if traceID == "" {
		traceID = newHex(16)
	}
	spanID := newHex(8)
	parent := t.SpanID(ctx)
	ns := &noopSpan{traceID: traceID, spanID: spanID, parent: parent, name: name}
	if t.Logger != nil {
		t.Logger.Debug("span start", "name", name, "trace_id", traceID, "span_id", spanID, "parent_span_id", parent)
	}
	return context.WithValue(ctx, traceKey{}, ns), ns
}

// TraceID implements Tracer.
func (t *Noop) TraceID(ctx context.Context) string {
	if s, ok := ctx.Value(traceKey{}).(*noopSpan); ok {
		return s.traceID
	}
	return ""
}

// SpanID implements Tracer.
func (t *Noop) SpanID(ctx context.Context) string {
	if s, ok := ctx.Value(traceKey{}).(*noopSpan); ok {
		return s.spanID
	}
	return ""
}

type noopSpan struct {
	traceID string
	spanID  string
	parent  string
	name    string
	ended   bool
}

func (s *noopSpan) Context() context.Context { return context.WithValue(context.Background(), traceKey{}, s) }

func (s *noopSpan) End()                 { s.ended = true }
func (s *noopSpan) AddEvent(string, map[string]string) {}
func (s *noopSpan) SetError(string)      {}

func newHex(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "0000000000000000"
	}
	return hex.EncodeToString(b)
}

// Global returns the process-wide default tracer (no-op). Components depend on
// the Tracer interface, so replacing this with an OTel tracer at startup is a
// one-line change.
var Global Tracer = &Noop{}
