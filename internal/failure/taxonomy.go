// Package failure defines the normalized failure taxonomy shared by the
// executor, observations, incidents and correlation. A small, stable set of
// classes keeps correlation deterministic and explainable.
package failure

// Class is a normalized failure category.
type Class string

// Taxonomy (extensible; new classes need to be added here, in the classifier,
// and to the OpenAPI enum).
const (
	DNSFailure          Class = "dns_failure"
	ConnectionTimeout   Class = "connection_timeout"
	ConnectionRefused   Class = "connection_refused"
	TLSFailure          Class = "tls_failure"
	HTTP4xx             Class = "http_4xx"
	HTTP5xx             Class = "http_5xx"
	LatencyExceeded     Class = "latency_exceeded"
	AssertionFailed     Class = "assertion_failed"
	NetworkError        Class = "network_error"
	ResponseTooLarge    Class = "response_too_large"
	InvalidResponse     Class = "invalid_response"
	SSRFBlocked         Class = "ssrf_blocked"
	Unknown             Class = "unknown"
)

// AllClasses lists every class (used for validation/docs).
var AllClasses = []Class{
	DNSFailure, ConnectionTimeout, ConnectionRefused, TLSFailure,
	HTTP4xx, HTTP5xx, LatencyExceeded, AssertionFailed, NetworkError,
	ResponseTooLarge, InvalidResponse, SSRFBlocked, Unknown,
}

// Valid reports whether c is a known class.
func Valid(c Class) bool {
	for _, v := range AllClasses {
		if v == c {
			return true
		}
	}
	return false
}

// Retryable reports whether a failure of class c should be retried.
// Retrying only transient infrastructure failures keeps retries safe and
// bounded; deterministic failures (4xx, assertions, config problems) fail
// fast.
func Retryable(c Class) bool {
	switch c {
	case DNSFailure, ConnectionTimeout, ConnectionRefused, HTTP5xx, NetworkError, TLSFailure:
		return true
	default:
		return false
	}
}
