package auth

import "regexp"

// emailRE is a pragmatic email shape check (RFC 5321-ish, no IDN handling in
// Phase 1). Delivery failures are handled at registration time by the caller.
var emailRE = regexp.MustCompile(`^[^@\s]+@[^@\s]+\.[^@\s]+$`)
