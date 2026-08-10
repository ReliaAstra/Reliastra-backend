// Package notifications implements asynchronous, idempotent notifications
// over the transactional outbox. A failed Slack POST must never affect an
// incident transaction: notifications are always written as outbox events and
// delivered by the notifier process with retries and dead-lettering.
package notifications

import (
	"time"
)

// Channel types.
const (
	ChannelEmail = "email"
	ChannelSlack = "slack"
)

// Delivery statuses.
const (
	DeliveryPending     = "pending"
	DeliverySending     = "sending"
	DeliverySent        = "sent"
	DeliveryFailed      = "failed"
	DeliveryRetrying    = "retrying"
	DeliveryDeadLetter  = "dead_letter"
)

// Channel is a configured notification destination for an org.
type Channel struct {
	ID             string    `json:"id"`
	OrganizationID string    `json:"organization_id"`
	Type           string    `json:"type"`
	Name           string    `json:"name"`
	Enabled        bool      `json:"enabled"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
	// Config is the decrypted destination config (never persisted plaintext).
	Config map[string]string `json:"-"`
}

// Delivery is one notification attempt record (idempotent per event+channel).
type Delivery struct {
	ID             string    `json:"id"`
	OrganizationID string    `json:"organization_id"`
	EventID        string    `json:"event_id"`
	ChannelID      string    `json:"channel_id"`
	EventType      string    `json:"event_type"`
	Status         string    `json:"status"`
	Attempt        int       `json:"attempt"`
	NextAttemptAt  *time.Time `json:"next_attempt_at,omitempty"`
	LastError      string    `json:"last_error,omitempty"`
	SentAt         *time.Time `json:"sent_at,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
}

// Message is a rendered notification payload.
type Message struct {
	Subject string
	Text    string
	Markdown string
}
