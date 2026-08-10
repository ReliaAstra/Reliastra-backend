package auth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Session is an opaque bearer session.
type Session struct {
	ID        string    `json:"id"`
	UserID    string    `json:"user_id"`
	ExpiresAt time.Time `json:"expires_at"`
	RevokedAt *time.Time `json:"revoked_at,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

// SessionStore persists sessions (token hash only).
type SessionStore struct {
	pool *pgxpool.Pool
}

// NewSessionStore builds a SessionStore.
func NewSessionStore(pool *pgxpool.Pool) *SessionStore { return &SessionStore{pool: pool} }

// HashToken returns the storage hash of a raw token.
func HashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

// Create inserts a session and returns the raw token (shown once) plus the
// session row.
func (s *SessionStore) Create(ctx context.Context, userID, ip, userAgent string, ttl time.Duration) (string, *Session, error) {
	raw := ids.NewToken(32)
	sess := &Session{
		ID:        ids.NewUUID(),
		UserID:    userID,
		ExpiresAt: time.Now().UTC().Add(ttl),
	}
	_, err := s.pool.Exec(ctx, `INSERT INTO sessions (id, user_id, token_hash, ip_address, user_agent, expires_at)
		VALUES ($1,$2,$3,$4,$5,$6)`,
		sess.ID, sess.UserID, HashToken(raw), ip, userAgent, sess.ExpiresAt)
	if err != nil {
		return "", nil, err
	}
	return raw, sess, nil
}

// Authenticate validates a raw token and returns the session. Expired or
// revoked sessions are rejected.
func (s *SessionStore) Authenticate(ctx context.Context, rawToken string) (*Session, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, user_id, expires_at, revoked_at, created_at
		FROM sessions WHERE token_hash = $1`, HashToken(rawToken))
	var sess Session
	err := row.Scan(&sess.ID, &sess.UserID, &sess.ExpiresAt, &sess.RevokedAt, &sess.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.Authentication("invalid_token", "invalid or expired session token")
	}
	if err != nil {
		return nil, err
	}
	if sess.RevokedAt != nil || sess.ExpiresAt.Before(time.Now().UTC()) {
		return nil, errors.Authentication("invalid_token", "invalid or expired session token")
	}
	return &sess, nil
}

// Revoke invalidates a session.
func (s *SessionStore) Revoke(ctx context.Context, rawToken string) error {
	_, err := s.pool.Exec(ctx, `UPDATE sessions SET revoked_at = now() WHERE token_hash = $1`, HashToken(rawToken))
	return err
}

// RevokeAllForUser revokes every active session for a user (password change).
func (s *SessionStore) RevokeAllForUser(ctx context.Context, userID string) error {
	_, err := s.pool.Exec(ctx, `UPDATE sessions SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL`, userID)
	return err
}
