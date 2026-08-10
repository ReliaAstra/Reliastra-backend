package monitors

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"strings"
	"syscall"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/failure"
)

// HTTPExecutor executes http monitors with SSRF-safe, timeout-bound, size-
// bounded HTTP requests and produces a normalized outcome. Phase timings are
// captured with net/http/httptrace (DNS, connect, TLS, TTFB).
type HTTPExecutor struct {
	resolver resolver
	dialFn   func(ctx context.Context, network, addr string) (net.Conn, error)
}

// NewHTTPExecutor builds the HTTP executor with the SSRF-safe dialer.
func NewHTTPExecutor() *HTTPExecutor {
	return &HTTPExecutor{resolver: netResolver{}}
}

// NewHTTPExecutorForTest builds an executor whose dialer bypasses the SSRF
// guard (the production guard blocks loopback/private destinations). Test
// only: used by integration tests that run target servers on localhost.
func NewHTTPExecutorForTest(dialFn func(ctx context.Context, network, addr string) (net.Conn, error)) *HTTPExecutor {
	return &HTTPExecutor{resolver: netResolver{}, dialFn: dialFn}
}

// Type implements Executor.
func (e *HTTPExecutor) Type() string { return "http" }

// Validate implements Executor.
func (e *HTTPExecutor) Validate(raw json.RawMessage) error {
	cfg, err := parseHTTPConfig(raw)
	if err != nil {
		return err
	}
	u, err := url.Parse(cfg.URL)
	if err != nil {
		return fmt.Errorf("invalid URL: %w", err)
	}
	if err := validateURL(u); err != nil {
		return err
	}
	if cfg.Method == "" {
		cfg.Method = "GET"
	}
	switch strings.ToUpper(cfg.Method) {
	case "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS":
	default:
		return fmt.Errorf("unsupported HTTP method %q", cfg.Method)
	}
	if len(cfg.ExpectedStatusCodes) == 0 {
		return fmt.Errorf("expected_status_codes must not be empty")
	}
	for _, c := range cfg.ExpectedStatusCodes {
		if c < 100 || c > 599 {
			return fmt.Errorf("invalid expected status code %d", c)
		}
	}
	if cfg.RedirectPolicy != "" && cfg.RedirectPolicy != "follow" && cfg.RedirectPolicy != "none" {
		return fmt.Errorf("redirect_policy must be 'follow' or 'none'")
	}
	if cfg.LatencyThresholdMS < 0 {
		return fmt.Errorf("latency_threshold_ms must be >= 0")
	}
	return nil
}

func parseHTTPConfig(raw json.RawMessage) (*HTTPConfig, error) {
	def := DefaultHTTPConfig()
	var cfg HTTPConfig
	if len(raw) == 0 {
		return &def, nil
	}
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&cfg); err != nil {
		return nil, fmt.Errorf("invalid monitor configuration: %w", err)
	}
	if cfg.Method == "" {
		cfg.Method = def.Method
	}
	if len(cfg.ExpectedStatusCodes) == 0 {
		cfg.ExpectedStatusCodes = def.ExpectedStatusCodes
	}
	if cfg.RedirectPolicy == "" {
		cfg.RedirectPolicy = def.RedirectPolicy
	}
	return &cfg, nil
}

// Execute implements Executor. spec.HTTP must be non-nil (guaranteed by the
// registry for type "http").
func (e *HTTPExecutor) Execute(ctx context.Context, spec *RuntimeSpec) (*CheckOutcome, error) {
	cfg := spec.HTTP
	if cfg == nil {
		return nil, errors.New("http executor: missing http configuration")
	}
	out := &CheckOutcome{Metadata: map[string]any{}}
	start := time.Now()

	u, err := url.Parse(cfg.URL)
	if err != nil {
		out.Success = false
		out.ErrorClass = string(failure.InvalidResponse)
		out.ErrorCode = "invalid_url"
		out.ErrorMessage = "invalid target URL"
		return out, nil
	}
	if err := validateURL(u); err != nil {
		out.Success = false
		out.ErrorClass = string(failure.SSRFBlocked)
		out.ErrorCode = "ssrf_blocked"
		out.ErrorMessage = err.Error()
		return out, nil
	}
	// Production executor validates the destination before dialing and
	// again at dial time (defeating DNS rebinding). Test executors install
	// a custom dialFn and are responsible for destination policy themselves.
	if e.dialFn == nil {
		if err := validateHostname(ctx, e.resolver, u.Host); err != nil {
			out.Success = false
			out.ErrorClass = string(failure.SSRFBlocked)
			out.ErrorCode = "ssrf_blocked"
			out.ErrorMessage = err.Error()
			return out, nil
		}
	}

	timeout := spec.Timeout
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// httptrace captures phase timings (per request; redirects restart the
	// connection but the overall latency_ms is the authoritative figure).
	var dnsStart, connStart, tlsStart time.Time
	trace := &httptrace.ClientTrace{
		DNSStart:          func(httptrace.DNSStartInfo) { dnsStart = time.Now() },
		DNSDone:           func(httptrace.DNSDoneInfo) { out.DNSMS = ms(time.Since(dnsStart)) },
		ConnectStart:      func(network, addr string) { connStart = time.Now() },
		ConnectDone:       func(network, addr string, err error) { out.ConnectMS = ms(time.Since(connStart)) },
		TLSHandshakeStart: func() { tlsStart = time.Now() },
		TLSHandshakeDone:  func(tls.ConnectionState, error) { out.TLSMS = ms(time.Since(tlsStart)) },
		GotFirstResponseByte: func() { out.TTFBMS = ms(time.Since(start)) },
	}
	ctx = httptrace.WithClientTrace(ctx, trace)

	dialer := &safeDialer{resolver: e.resolver, timeout: timeout}
	dial := dialer.DialContext
	if e.dialFn != nil {
		dial = e.dialFn
	}
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment, // honor egress proxy in cloud deployments
		DialContext:           dial,
		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 15 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		MaxIdleConns:          50,
		IdleConnTimeout:       60 * time.Second,
		DisableKeepAlives:     true, // checks are stateless; avoid cross-tenant connection reuse
		TLSClientConfig:       &tls.Config{MinVersion: tls.VersionTLS12, InsecureSkipVerify: cfg.TLSSkipVerify},
		ForceAttemptHTTP2:     !cfg.TLSSkipVerify,
	}
	defer transport.CloseIdleConnections()

	maxRedirects := spec.MaxRedirects
	if maxRedirects <= 0 {
		maxRedirects = 5
	}
	redirectPolicy := cfg.RedirectPolicy == "follow"

	client := &http.Client{
		Transport: transport,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if !redirectPolicy {
				return http.ErrUseLastResponse
			}
			if len(via) >= maxRedirects {
				return errors.New("stopped after too many redirects")
			}
			if e.dialFn == nil {
				if err := validateRedirectURL(ctx, e.resolver, req.URL.String()); err != nil {
					return err
				}
			}
			return nil
		},
	}

	method := strings.ToUpper(cfg.Method)
	if method == "" {
		method = "GET"
	}
	var body io.Reader
	if cfg.Body != "" || spec.SecretBody != "" {
		b := cfg.Body
		if cfg.BodySensitive && spec.SecretBody != "" {
			b = spec.SecretBody
		}
		body = strings.NewReader(b)
	}

	req, err := http.NewRequestWithContext(ctx, method, cfg.URL, body)
	if err != nil {
		out.Success = false
		out.ErrorClass = string(failure.InvalidResponse)
		out.ErrorCode = "invalid_request"
		out.ErrorMessage = err.Error()
		return out, nil
	}
	// Headers: explicit config + decrypted secrets (secrets win).
	for k, v := range cfg.Headers {
		req.Header.Set(k, v)
	}
	for k, v := range spec.Secrets {
		req.Header.Set(k, v)
	}

	resp, err := client.Do(req)
	if err != nil {
		finishOutcome(out, err)
		out.LatencyMS = ms(time.Since(start))
		return out, nil
	}
	defer resp.Body.Close()

	limit := spec.MaxResponseBytes
	if limit <= 0 {
		limit = 1 << 20
	}
	bodyBytes, readErr := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	overLimit := int64(len(bodyBytes)) > limit

	out.StatusCode = resp.StatusCode
	out.ResponseSize = int64(len(bodyBytes))
	out.LatencyMS = ms(time.Since(start))
	if out.TTFBMS == 0 {
		out.TTFBMS = out.LatencyMS
	}

	// Assertions.
	statusOK := statusMatches(cfg.ExpectedStatusCodes, resp.StatusCode)
	var assertionErrors []string
	if !statusOK {
		assertionErrors = append(assertionErrors, fmt.Sprintf("expected status %v, got %d", cfg.ExpectedStatusCodes, resp.StatusCode))
	}
	bodyStr := string(bodyBytes)
	for _, sub := range cfg.ResponseBodyAssertions {
		if !strings.Contains(bodyStr, sub) {
			assertionErrors = append(assertionErrors, fmt.Sprintf("response body missing %q", sub))
		}
	}
	for k, want := range cfg.ResponseHeaderAssertions {
		if got := resp.Header.Get(k); got != want {
			assertionErrors = append(assertionErrors, fmt.Sprintf("header %q = %q, want %q", k, got, want))
		}
	}
	latencyExceeded := cfg.LatencyThresholdMS > 0 && out.LatencyMS > cfg.LatencyThresholdMS
	if latencyExceeded {
		assertionErrors = append(assertionErrors,
			fmt.Sprintf("latency %dms exceeded threshold %dms", out.LatencyMS, cfg.LatencyThresholdMS))
	}
	out.AssertionsFailed = len(assertionErrors)
	totalAssertions := 1 + len(cfg.ResponseBodyAssertions) + len(cfg.ResponseHeaderAssertions)
	if latencyExceeded {
		totalAssertions++
	}
	out.AssertionsPassed = totalAssertions - len(assertionErrors)

	if readErr != nil || overLimit {
		out.Success = false
		out.ErrorClass = string(failure.ResponseTooLarge)
		out.ErrorCode = "response_too_large"
		out.ErrorMessage = "response body exceeded the configured limit"
		return out, nil
	}
	if len(assertionErrors) > 0 {
		out.Success = false
		switch {
		case latencyExceeded:
			out.ErrorClass = string(failure.LatencyExceeded)
			out.ErrorCode = "latency_exceeded"
		case !statusOK && resp.StatusCode >= 500:
			out.ErrorClass = string(failure.HTTP5xx)
			out.ErrorCode = "http_5xx"
		case !statusOK && resp.StatusCode >= 400:
			out.ErrorClass = string(failure.HTTP4xx)
			out.ErrorCode = "http_4xx"
		default:
			out.ErrorClass = string(failure.AssertionFailed)
			out.ErrorCode = "assertion_failed"
		}
		out.ErrorMessage = strings.Join(assertionErrors, "; ")
		return out, nil
	}

	out.Success = true
	return out, nil
}

func statusMatches(want []int, got int) bool {
	for _, c := range want {
		if got == c {
			return true
		}
	}
	return false
}

// finishOutcome normalizes a transport error into the taxonomy.
func finishOutcome(out *CheckOutcome, err error) {
	out.Success = false
	out.ErrorMessage = sanitizeError(err)
	var ssrf *SSRFError
	var netErr net.Error
	var dnsErr *net.DNSError
	var certErr x509.UnknownAuthorityError
	var hostErr x509.HostnameError
	var certInvalidErr x509.CertificateInvalidError
	switch {
	case errors.As(err, &ssrf):
		out.ErrorClass = string(failure.SSRFBlocked)
		out.ErrorCode = "ssrf_blocked"
	case errors.As(err, &dnsErr):
		out.ErrorClass = string(failure.DNSFailure)
		out.ErrorCode = "dns_failure"
	case errors.As(err, &certErr), errors.As(err, &hostErr), errors.As(err, &certInvalidErr):
		out.ErrorClass = string(failure.TLSFailure)
		out.ErrorCode = "tls_failure"
	case errors.Is(err, syscall.ECONNREFUSED):
		out.ErrorClass = string(failure.ConnectionRefused)
		out.ErrorCode = "connection_refused"
	case errors.As(err, &netErr) && netErr.Timeout():
		out.ErrorClass = string(failure.ConnectionTimeout)
		out.ErrorCode = "connection_timeout"
	case strings.Contains(err.Error(), "redirect"):
		out.ErrorClass = string(failure.NetworkError)
		out.ErrorCode = "redirect_error"
	default:
		out.ErrorClass = string(failure.NetworkError)
		out.ErrorCode = "network_error"
	}
}

func ms(d time.Duration) int {
	if d <= 0 {
		return 0
	}
	return int(d.Milliseconds())
}

// sanitizeError strips URLs/credentials that may appear in net/http errors.
func sanitizeError(err error) string {
	if err == nil {
		return ""
	}
	s := err.Error()
	if i := strings.Index(s, "\""); i >= 0 {
		s = s[:i]
	}
	if len(s) > 512 {
		s = s[:512]
	}
	return s
}
