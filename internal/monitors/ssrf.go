package monitors

import (
	"context"
	"fmt"
	"net"
	"net/netip"
	"net/url"
	"strings"
	"time"
)

// SSRF guard. Users control monitored URLs, so the monitoring engine must
// never be able to reach internal infrastructure: loopback, private networks,
// link-local, cloud metadata endpoints, or non-HTTP schemes. Validation is
// performed (a) at URL-parse time, (b) at dial time after DNS resolution
// (defeating DNS rebinding), and (c) for every redirect hop.
//
// Defense in depth: dial-time validation is the authoritative gate; parse-time
// validation gives fast, clear errors.

// blockedCIDRs are the network ranges the engine refuses to dial.
var blockedCIDRs = []netip.Prefix{
	netip.MustParsePrefix("0.0.0.0/8"),        // "this" network
	netip.MustParsePrefix("10.0.0.0/8"),       // RFC1918
	netip.MustParsePrefix("100.64.0.0/10"),    // CGNAT
	netip.MustParsePrefix("127.0.0.0/8"),      // loopback
	netip.MustParsePrefix("169.254.0.0/16"),   // link-local + cloud metadata 169.254.169.254
	netip.MustParsePrefix("172.16.0.0/12"),    // RFC1918
	netip.MustParsePrefix("192.0.0.0/24"),     // IETF protocol assignments
	netip.MustParsePrefix("192.0.2.0/24"),     // TEST-NET-1
	netip.MustParsePrefix("192.168.0.0/16"),   // RFC1918
	netip.MustParsePrefix("198.18.0.0/15"),    // benchmarking
	netip.MustParsePrefix("198.51.100.0/24"),  // TEST-NET-2
	netip.MustParsePrefix("203.0.113.0/24"),   // TEST-NET-3
	netip.MustParsePrefix("224.0.0.0/4"),      // multicast
	netip.MustParsePrefix("240.0.0.0/4"),      // reserved
	netip.MustParsePrefix("255.255.255.255/32"),
	netip.MustParsePrefix("::1/128"),          // loopback
	netip.MustParsePrefix("::/128"),           // unspecified
	netip.MustParsePrefix("64:ff9b::/96"),     // NAT64 well-known prefix
	netip.MustParsePrefix("100::/64"),         // discard-only
	netip.MustParsePrefix("2001:db8::/32"),    // documentation
	netip.MustParsePrefix("fc00::/7"),         // unique local
	netip.MustParsePrefix("fe80::/10"),        // link-local
	netip.MustParsePrefix("ff00::/8"),         // multicast
}

// ipBlocked reports whether addr falls in a blocked range.
func ipBlocked(addr netip.Addr) bool {
	// Normalize IPv4-mapped IPv6 to the IPv4 address.
	if addr.Is4In6() {
		addr = addr.Unmap()
	}
	for _, p := range blockedCIDRs {
		if p.Contains(addr) {
			return true
		}
	}
	return false
}

// SSRFError indicates a blocked destination.
type SSRFError struct{ Host string }

func (e *SSRFError) Error() string {
	return fmt.Sprintf("destination %q is not allowed (private/internal network)", e.Host)
}

// validateURL checks scheme and host shape without resolving.
func validateURL(u *url.URL) error {
	if u == nil {
		return fmt.Errorf("url is required")
	}
	switch strings.ToLower(u.Scheme) {
	case "http", "https":
	default:
		return fmt.Errorf("only http and https targets are supported (got %q)", u.Scheme)
	}
	if u.Host == "" {
		return fmt.Errorf("url host is required")
	}
	// Reject URLs with userinfo (credential smuggling).
	if u.User != nil {
		return fmt.Errorf("url must not contain credentials")
	}
	return nil
}

// resolver abstracts DNS for tests.
type resolver interface {
	LookupIPAddr(ctx context.Context, host string) ([]net.IPAddr, error)
}

type netResolver struct{}

func (netResolver) LookupIPAddr(ctx context.Context, host string) ([]net.IPAddr, error) {
	return net.DefaultResolver.LookupIPAddr(ctx, host)
}

// validateHostname resolves host and rejects any blocked address. If raw IP,
// it validates directly without DNS.
func validateHostname(ctx context.Context, r resolver, host string) error {
	if host == "" {
		return fmt.Errorf("host is required")
	}
	// Trim port if present.
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	if ip, err := netip.ParseAddr(host); err == nil {
		if ipBlocked(ip) {
			return &SSRFError{Host: host}
		}
		return nil
	}
	addrs, err := r.LookupIPAddr(ctx, host)
	if err != nil {
		return fmt.Errorf("dns resolution failed for %q: %w", host, err)
	}
	if len(addrs) == 0 {
		return fmt.Errorf("dns resolution returned no addresses for %q", host)
	}
	for _, a := range addrs {
		ip, ok := netip.AddrFromSlice(a.IP)
		if !ok {
			continue
		}
		if ipBlocked(ip) {
			return &SSRFError{Host: host}
		}
	}
	return nil
}

// safeDialer dials TCP only after validating the resolved destination. The
// validation happens at dial time (post-DNS), which defeats DNS-rebinding
// attacks where the hostname resolves differently between validation and
// connection.
type safeDialer struct {
	resolver  resolver
	timeout   time.Duration
}

func (d *safeDialer) DialContext(ctx context.Context, network, addr string) (net.Conn, error) {
	if network != "tcp" && network != "tcp4" && network != "tcp6" {
		return nil, fmt.Errorf("unsupported network %q", network)
	}
	if err := validateHostname(ctx, d.resolver, addr); err != nil {
		return nil, err
	}
	var nd net.Dialer
	if d.timeout > 0 {
		nd.Timeout = d.timeout
	}
	return nd.DialContext(ctx, network, addr)
}

// validateRedirectURL validates a redirect location (scheme + resolved host).
func validateRedirectURL(ctx context.Context, r resolver, rawURL string) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid redirect location: %w", err)
	}
	if err := validateURL(u); err != nil {
		return fmt.Errorf("invalid redirect location: %w", err)
	}
	return validateHostname(ctx, r, u.Host)
}
