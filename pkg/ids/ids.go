// Package ids generates random identifiers for the Reliastra platform.
//
// All identifiers are 128-bit random values formatted as canonical RFC 4122
// version-4 UUIDs. They are generated from crypto/rand and never from a weak
// PRNG. UUIDs are opaque to clients; ordering is always carried by dedicated
// timestamp columns (created_at, scheduled_for, ...).
package ids

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
)

// NewUUID returns a new random version-4 UUID string, e.g. "9b2e...".
func NewUUID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		// crypto/rand failure is unrecoverable for a security-sensitive
		// platform; panic loudly rather than silently reusing state.
		panic(fmt.Sprintf("ids: crypto/rand unavailable: %v", err))
	}
	b[6] = (b[6] & 0x0f) | 0x40 // version 4
	b[8] = (b[8] & 0x3f) | 0x80 // variant 10
	return formatUUID(b)
}

// NewToken returns a random opaque token of n bytes (hex-encoded), used for
// session tokens and API key secrets. n must be >= 16.
func NewToken(n int) string {
	if n < 16 {
		n = 16
	}
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("ids: crypto/rand unavailable: %v", err))
	}
	return hex.EncodeToString(b)
}

// NewAPIKey returns a prefixed, human-typable API key secret:
// "relia_" + 32 random bytes base32-encoded (lowercase, no padding).
func NewAPIKey() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("ids: crypto/rand unavailable: %v", err))
	}
	const alphabet = "abcdefghijklmnopqrstuvwxyz234567"
	var sb strings.Builder
	sb.WriteString("relia_")
	for _, by := range b {
		sb.WriteByte(alphabet[int(by)&31])
	}
	return sb.String()
}

func formatUUID(b [16]byte) string {
	var dst [36]byte
	hex.Encode(dst[0:8], b[0:4])
	dst[8] = '-'
	hex.Encode(dst[9:13], b[4:6])
	dst[13] = '-'
	hex.Encode(dst[14:18], b[6:8])
	dst[18] = '-'
	hex.Encode(dst[19:23], b[8:10])
	dst[23] = '-'
	hex.Encode(dst[24:36], b[10:16])
	return string(dst[:])
}
