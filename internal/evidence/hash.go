package evidence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

// HashAlgorithm is the canonical integrity algorithm.
const HashAlgorithm = "sha256"

// CanonicalBytes serializes the package deterministically (fixed struct field
// order, UTC RFC3339 timestamps). The returned bytes are exactly what is
// stored in object storage, so verification is byte-for-byte: the SHA-256 of
// the stored artifact equals the hash recorded in evidence_records.
//
// The authoritative hash lives in evidence_records (hash + algorithm +
// version + created_at). The artifact declares the algorithm in its
// integrity section; embedding the hash itself would make the digest
// self-referential.
func CanonicalBytes(pkg *Package) ([]byte, error) {
	pkg.Integrity = IntegritySection{HashAlgorithm: HashAlgorithm}
	return json.Marshal(pkg)
}

// HashPackage returns the canonical bytes and their SHA-256 hex digest.
func HashPackage(pkg *Package) (hash string, canonical []byte, err error) {
	raw, err := CanonicalBytes(pkg)
	if err != nil {
		return "", nil, err
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), raw, nil
}

// VerifyBytes checks that data matches an expected SHA-256 hex digest.
func VerifyBytes(data []byte, expectedHash string) bool {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]) == expectedHash
}
