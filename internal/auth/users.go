package auth

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// User is an authenticated identity.
type User struct {
	ID           string    `json:"id"`
	Email        string    `json:"email"`
	Name         string    `json:"name"`
	PasswordHash string    `json:"-"`
	Status       string    `json:"status"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// UserStore persists users.
type UserStore struct {
	pool *pgxpool.Pool
}

// NewUserStore builds a UserStore.
func NewUserStore(pool *pgxpool.Pool) *UserStore { return &UserStore{pool: pool} }

// Create inserts a user; returns conflict error when email is taken.
func (s *UserStore) Create(ctx context.Context, email, passwordHash, name string) (*User, error) {
	u := &User{ID: ids.NewUUID(), Email: email, PasswordHash: passwordHash, Name: name, Status: "active"}
	_, err := s.pool.Exec(ctx, `INSERT INTO users (id, email, password_hash, name)
		VALUES ($1, $2, $3, $4)`, u.ID, u.Email, u.PasswordHash, u.Name)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, errors.Conflict("email_taken", "an account with this email already exists")
		}
		return nil, err
	}
	return u, nil
}

// ByEmail looks up a user by normalized (lowercase) email.
func (s *UserStore) ByEmail(ctx context.Context, email string) (*User, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, email, name, password_hash, status, created_at, updated_at
		FROM users WHERE lower(email) = lower($1)`, email)
	return scanUser(row)
}

// ByID looks up a user by id.
func (s *UserStore) ByID(ctx context.Context, id string) (*User, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, email, name, password_hash, status, created_at, updated_at
		FROM users WHERE id = $1`, id)
	u, err := scanUser(row)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("user_not_found", "user not found")
	}
	return u, err
}

func scanUser(row pgx.Row) (*User, error) {
	var u User
	err := row.Scan(&u.ID, &u.Email, &u.Name, &u.PasswordHash, &u.Status, &u.CreatedAt, &u.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("user_not_found", "user not found")
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}
