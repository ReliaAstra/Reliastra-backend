package monitors

import (
	"net/url"
	"context"
	"net"
	"net/netip"
	"testing"
)

// fakeResolver returns fixed addresses for a host.
type fakeResolver struct{ addrs []net.IPAddr }

func (f *fakeResolver) LookupIPAddr(_ context.Context, _ string) ([]net.IPAddr, error) {
	return f.addrs, nil
}

func TestIPBlocked(t *testing.T) {
	blocked := []string{
		"127.0.0.1", "127.0.0.2", "10.0.0.1", "10.255.255.255",
		"172.16.0.1", "172.31.255.255", "192.168.1.1", "169.254.169.254",
		"0.0.0.0", "192.0.2.1", "198.51.100.1", "203.0.113.1",
		"::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", // IPv4-mapped loopback
		"2001:db8::1",
	}
	allowed := []string{
		"8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111",
	}
	for _, s := range blocked {
		addr, err := netip.ParseAddr(s)
		if err != nil {
			t.Fatalf("parse %s: %v", s, err)
		}
		if !ipBlocked(addr) {
			t.Errorf("expected %s to be blocked", s)
		}
	}
	for _, s := range allowed {
		addr, err := netip.ParseAddr(s)
		if err != nil {
			t.Fatalf("parse %s: %v", s, err)
		}
		if ipBlocked(addr) {
			t.Errorf("expected %s to be allowed", s)
		}
	}
}

func TestValidateHostnameDNSRebinding(t *testing.T) {
	// The hostname resolves to a private address: must be rejected even
	// though the string itself looks public.
	r := &fakeResolver{addrs: []net.IPAddr{{IP: net.ParseIP("10.1.2.3")}}}
	if err := validateHostname(context.Background(), r, "evil.example.com"); err == nil {
		t.Error("expected SSRF rejection for DNS resolving to private IP")
	}
	// Public resolution: allowed.
	r2 := &fakeResolver{addrs: []net.IPAddr{{IP: net.ParseIP("8.8.8.8")}}}
	if err := validateHostname(context.Background(), r2, "good.example.com"); err != nil {
		t.Errorf("unexpected rejection: %v", err)
	}
}

func TestValidateURL(t *testing.T) {
	for _, bad := range []string{
		"ftp://example.com", "file:///etc/passwd", "http://user:pass@example.com",
		"", "http://",
	} {
		u, _ := parseRaw(bad)
		if err := validateURL(u); err == nil {
			t.Errorf("expected rejection for %q", bad)
		}
	}
	for _, good := range []string{"http://example.com", "https://example.com/path?q=1"} {
		u, _ := parseRaw(good)
		if err := validateURL(u); err != nil {
			t.Errorf("unexpected rejection for %q: %v", good, err)
		}
	}
}

func parseRaw(s string) (*url.URL, error) { return url.Parse(s) }
