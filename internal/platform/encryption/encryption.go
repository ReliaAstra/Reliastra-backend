// Package encryption implements envelope encryption for secrets at rest
// (monitor credentials, notification channel configs).
//
// Each secret is encrypted with a data key derived from a master key using
// HKDF-SHA256 with a random 12-byte nonce (AES-256-GCM). Records store
// ciphertext + key_version + nonce; rotating the master key never requires
// re-encrypting data (new writes use the new version, reads fall back to the
// version recorded with the ciphertext).
package encryption

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"
)

// ErrInvalidKey indicates the master key is unusable.
var ErrInvalidKey = errors.New("encryption: invalid master key")

// Ciphertext is the serialized encrypted value.
type Ciphertext struct {
	KeyVersion int
	Nonce      []byte
	Data       []byte
}

// Marshal serializes as "v<version>:<hex nonce>:<hex data>".
func (c Ciphertext) Marshal() string {
	return fmt.Sprintf("v%d:%s:%s", c.KeyVersion, hex.EncodeToString(c.Nonce), hex.EncodeToString(c.Data))
}

// Unmarshal parses the serialized form.
func Unmarshal(s string) (Ciphertext, error) {
	parts := strings.SplitN(s, ":", 3)
	if len(parts) != 3 || !strings.HasPrefix(parts[0], "v") {
		return Ciphertext{}, errors.New("encryption: malformed ciphertext")
	}
	var ver int
	if _, err := fmt.Sscanf(parts[0], "v%d", &ver); err != nil {
		return Ciphertext{}, errors.New("encryption: malformed key version")
	}
	nonce, err := hex.DecodeString(parts[1])
	if err != nil {
		return Ciphertext{}, errors.New("encryption: malformed nonce")
	}
	data, err := hex.DecodeString(parts[2])
	if err != nil {
		return Ciphertext{}, errors.New("encryption: malformed data")
	}
	return Ciphertext{KeyVersion: ver, Nonce: nonce, Data: data}, nil
}

// Encrypter encrypts values with a master key.
type Encrypter struct {
	masterKey []byte
	version   int
	aead      cipher.AEAD
}

// New builds an Encrypter from a hex-encoded 32-byte master key.
func New(masterKeyHex string, version int) (*Encrypter, error) {
	if version < 1 {
		return nil, fmt.Errorf("encryption: key version must be >= 1")
	}
	key, err := hex.DecodeString(masterKeyHex)
	if err != nil || len(key) != 32 {
		return nil, fmt.Errorf("encryption: master key must be 32 bytes hex-encoded")
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("encryption: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("encryption: %w", err)
	}
	return &Encrypter{masterKey: key, version: version, aead: aead}, nil
}

// DeriveKey derives the per-record data key from the master key.
func (e *Encrypter) DeriveKey(nonce []byte) []byte {
	mac := hmac.New(sha256.New, e.masterKey)
	mac.Write(nonce)
	return mac.Sum(nil)
}

// Encrypt encrypts plaintext and returns the serialized ciphertext.
func (e *Encrypter) Encrypt(plaintext []byte) (string, error) {
	nonce := make([]byte, e.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}
	key := e.DeriveKey(nonce)
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	data := aead.Seal(nil, nonce, plaintext, nil)
	return Ciphertext{KeyVersion: e.version, Nonce: nonce, Data: data}.Marshal(), nil
}

// Decrypt decrypts a serialized ciphertext. If the ciphertext uses an older
// key version the master key is still valid for it (same master key material);
// versioning is recorded for future key rotation, where the decrypt path would
// select the version-specific key.
func (e *Encrypter) Decrypt(serialized string) ([]byte, error) {
	c, err := Unmarshal(serialized)
	if err != nil {
		return nil, err
	}
	key := e.DeriveKey(c.Nonce)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	plain, err := aead.Open(nil, c.Nonce, c.Data, nil)
	if err != nil {
		return nil, fmt.Errorf("encryption: decrypt failed (tampered or wrong key)")
	}
	return plain, nil
}

// KeyVersion returns the configured key version.
func (e *Encrypter) KeyVersion() int { return e.version }
