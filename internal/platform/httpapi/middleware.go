package httpapi

import (
	"context"
	"log/slog"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/auth"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/ratelimit"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
	"github.com/ReliaAstra/reliastra-backend/pkg/logging"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

type ctxKey string

const (
	ctxRequestID  ctxKey = "request_id"
	ctxPrincipal  ctxKey = "principal"
	ctxOrgID      ctxKey = "org_id"
	ctxLogger     ctxKey = "logger"
)

// RequestID returns the request id from the context.
func RequestID(ctx context.Context) string {
	v, _ := ctx.Value(ctxRequestID).(string)
	return v
}

// Principal returns the authenticated principal from the context.
func Principal(ctx context.Context) *auth.Principal {
	p, _ := ctx.Value(ctxPrincipal).(*auth.Principal)
	return p
}

// OrgID returns the resolved current organization id.
func OrgID(ctx context.Context) string {
	v, _ := ctx.Value(ctxOrgID).(string)
	return v
}

// Logger returns the request-scoped logger.
func Logger(ctx context.Context) *slog.Logger {
	l, _ := ctx.Value(ctxLogger).(*slog.Logger)
	return l
}

// Dependencies for middleware.
type MiddlewareDeps struct {
	Logger   *slog.Logger
	Auth     *auth.Service
	Limiter  ratelimit.Limiter
	RateCfg  config.RateLimitConfig
	CORS     config.CORSConfig
	HTTP     config.HTTPConfig
	Now      func() time.Time
}

// WithRequestID generates or preserves a request id.
func WithRequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rid := r.Header.Get("X-Request-Id")
		if rid == "" || len(rid) > 128 {
			rid = ids.NewUUID()
		}
		ctx := context.WithValue(r.Context(), ctxRequestID, rid)
		w.Header().Set("X-Request-Id", rid)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// WithLogging attaches a request-scoped logger and logs the request line.
func WithLogging(deps MiddlewareDeps) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			sw := &statusWriter{ResponseWriter: w, status: 200}
			ctx := context.WithValue(r.Context(), ctxLogger, deps.Logger)
			next.ServeHTTP(sw, r.WithContext(ctx))
			latency := time.Since(start)
			logger := logging.WithContext(deps.Logger, r.Context())
			logger.Info("http request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", sw.status,
				"latency_ms", latency.Milliseconds(),
				"remote", ClientIP(r, deps.HTTP.TrustedProxyHeaders),
			)
			metrics.APIRequestsTotal.WithLabelValues(r.Method, routePattern(r), http.StatusText(sw.status)).Inc()
			metrics.APIRequestDuration.WithLabelValues(r.Method, routePattern(r)).Observe(latency.Seconds())
		})
	}
}

// WithRecovery converts panics into 500 responses.
func WithRecovery(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if rec := recover(); rec != nil {
					logger.Error("panic recovered", "panic", rec, "path", r.URL.Path)
					WriteError(w, logger, RequestID(r.Context()), errors.Internal("internal_error", "an unexpected error occurred"))
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}

// WithSecurityHeaders sets baseline security headers.
func WithSecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "DENY")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
}

// WithCORS handles preflight and CORS headers.
func WithCORS(cfg config.CORSConfig) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if origin != "" {
				if allowsOrigin(cfg.AllowedOrigins, origin) {
					h := w.Header()
					h.Set("Access-Control-Allow-Origin", origin)
					h.Set("Vary", "Origin")
					h.Set("Access-Control-Allow-Headers", strings.Join(cfg.AllowedHeaders, ", "))
					h.Set("Access-Control-Allow-Methods", "GET, POST, PATCH, PUT, DELETE, OPTIONS")
					h.Set("Access-Control-Max-Age", itoa(cfg.MaxAgeSeconds))
				}
				if r.Method == http.MethodOptions {
					w.WriteHeader(http.StatusNoContent)
					return
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

// WithBodyLimit caps request bodies.
func WithBodyLimit(maxBytes int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if maxBytes > 0 {
				r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			}
			next.ServeHTTP(w, r)
		})
	}
}

// WithRateLimit applies rate limits per scope. scopes:
//
//	auth    -> strict per-IP limit for authentication endpoints
//	public  -> per-IP limit for unauthenticated public endpoints
//	api     -> per-IP + per-user + per-org + per-key limits
func WithRateLimit(deps MiddlewareDeps, scope string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !deps.RateCfg.Enabled {
				next.ServeHTTP(w, r)
				return
			}
			ip := ClientIP(r, deps.HTTP.TrustedProxyHeaders)
			window := time.Minute
			var checks []struct {
				key   string
				limit int
			}
			switch scope {
			case "auth":
				checks = append(checks, struct {
					key   string
					limit int
				}{"rl:auth:ip:" + ip, deps.RateCfg.AuthPerIPPerMinute})
			case "public":
				checks = append(checks, struct {
					key   string
					limit int
				}{"rl:public:ip:" + ip, deps.RateCfg.PublicPerMinute})
			default:
				checks = append(checks, struct {
					key   string
					limit int
				}{"rl:api:ip:" + ip, deps.RateCfg.PerIPPerMinute})
				if p := Principal(r.Context()); p != nil {
					if p.UserID != "" {
						checks = append(checks, struct {
							key   string
							limit int
						}{"rl:api:user:" + p.UserID, deps.RateCfg.PerUserPerMinute})
					}
					if p.OrganizationID != "" {
						checks = append(checks, struct {
							key   string
							limit int
						}{"rl:api:org:" + p.OrganizationID, deps.RateCfg.PerOrgPerMinute})
					}
					if p.APIKeyID != "" {
						checks = append(checks, struct {
							key   string
							limit int
						}{"rl:api:key:" + p.APIKeyID, deps.RateCfg.PerAPIKeyPerMinute})
					}
				}
			}
			for _, c := range checks {
				res, err := deps.Limiter.Allow(r.Context(), c.key, c.limit, window)
				if err != nil {
					// Limiter failure must not take the API down; log and allow.
					deps.Logger.Warn("rate limiter error", "error", err.Error())
					continue
				}
				if !res.Allowed {
					w.Header().Set("Retry-After", itoa(int(res.RetryAfter/time.Second)))
					WriteError(w, deps.Logger, RequestID(r.Context()),
						errors.RateLimited("rate_limited", "rate limit exceeded", int(res.RetryAfter/time.Second)))
					return
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

// WithAuthn authenticates the bearer token and attaches a Principal.
func WithAuthn(deps MiddlewareDeps) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			token := auth.ParseBearer(r.Header.Get("Authorization"))
			if token == "" {
				WriteError(w, deps.Logger, RequestID(r.Context()),
					errors.Authentication("missing_credentials", "authentication required (Bearer token)"))
				return
			}
			p, err := deps.Auth.AuthenticateToken(r.Context(), token)
			if err != nil {
				WriteError(w, deps.Logger, RequestID(r.Context()), err)
				return
			}
			ctx := context.WithValue(r.Context(), ctxPrincipal, p)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// WithOrgScope resolves the current organization for the principal and
// attaches it to the context.
func WithOrgScope(deps MiddlewareDeps) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			p := Principal(r.Context())
			if p == nil {
				WriteError(w, deps.Logger, RequestID(r.Context()),
					errors.Authentication("missing_credentials", "authentication required"))
				return
			}
			requested := r.Header.Get("X-Reliasorg")
			if p.AuthMethod == "api_key" {
				// The API key row carries the org; look it up to enforce it.
				key, err := deps.Auth.APIKeyByID(r.Context(), p.APIKeyID)
				if err != nil {
					WriteError(w, deps.Logger, RequestID(r.Context()), err)
					return
				}
				if err := deps.Auth.SetAPIKeyOrg(r.Context(), p, key.OrganizationID, requested); err != nil {
					WriteError(w, deps.Logger, RequestID(r.Context()), err)
					return
				}
			} else {
				if err := deps.Auth.ResolveOrgScope(r.Context(), p, requested); err != nil {
					WriteError(w, deps.Logger, RequestID(r.Context()), err)
					return
				}
			}
			ctx := logging.WithOrg(r.Context(), p.OrganizationID)
			ctx = context.WithValue(ctx, ctxOrgID, p.OrganizationID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// statusWriter records the response status.
type statusWriter struct {
	http.ResponseWriter
	status int
}

func (s *statusWriter) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

// ClientIP extracts the client IP, honoring the proxy header setting.
func ClientIP(r *http.Request, trustProxy bool) string {
	if trustProxy {
		if fwd := r.Header.Get("X-Forwarded-For"); fwd != "" {
			parts := strings.Split(fwd, ",")
			if ip := net.ParseIP(strings.TrimSpace(parts[0])); ip != nil {
				return ip.String()
			}
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// routePattern returns a sanitized route pattern for metrics cardinality.
func routePattern(r *http.Request) string {
	p := r.URL.Path
	if len(p) > 64 {
		return "other"
	}
	return p
}

func allowsOrigin(allowed []string, origin string) bool {
	if len(allowed) == 0 {
		return false
	}
	for _, a := range allowed {
		if a == "*" || a == origin {
			return true
		}
	}
	return false
}

func itoa(n int) string { return strconv.Itoa(n) }
