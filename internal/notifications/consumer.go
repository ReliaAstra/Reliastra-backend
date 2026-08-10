package notifications

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/evidence"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// NotifiableEvents are outbox event types that fan out to channels.
var NotifiableEvents = map[string]bool{
	"incident.created":        true,
	"incident.confirmed":      true,
	"incident.resolved":       true,
	"incident.false_positive": true,
	"evidence.generated":      true,
	"monitor.failed":          true,
	"monitor.recovered":       true,
}

// EvidenceTriggerEvents are outbox events that trigger evidence generation.
var EvidenceTriggerEvents = map[string]bool{
	"incident.confirmed":  true,
	"incident.resolved":   true,
	"evidence.requested":  true,
}

// Consumer drains the transactional outbox: it fans events out to notification
// channels and triggers async evidence generation. A failed provider never
// breaks the event flow; deliveries retry with backoff and eventually
// dead-letter.
type Consumer struct {
	outbox   *outbox.Store
	store    *Store
	evidence *evidence.Service
	providers map[string]Provider
	cfg      config.NotifierConfig
	logger   *slog.Logger
	now      func() time.Time
}

// NewConsumer builds the outbox consumer.
func NewConsumer(outbox *outbox.Store, store *Store, evidenceSvc *evidence.Service,
	providers []Provider, cfg config.NotifierConfig, logger *slog.Logger) *Consumer {
	pm := map[string]Provider{}
	for _, p := range providers {
		pm[p.Type()] = p
	}
	return &Consumer{
		outbox: outbox, store: store, evidence: evidenceSvc, providers: pm,
		cfg: cfg, logger: logger, now: time.Now,
	}
}

// ProcessOnce handles one batch of outbox events and deliveries (used by
// tests and by Run's loop).
func (c *Consumer) ProcessOnce(ctx context.Context) error {
	if err := c.processOutbox(ctx); err != nil {
		return err
	}
	return c.processDeliveries(ctx)
}

// Run polls the outbox and delivery queues until ctx is cancelled.
func (c *Consumer) Run(ctx context.Context) error {
	t := time.NewTicker(c.cfg.PollInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-t.C:
			if err := c.ProcessOnce(ctx); err != nil {
				c.logger.Error("notifier cycle failed", "error", err.Error())
			}
		}
	}
}

// processOutbox handles one batch of pending outbox events.
func (c *Consumer) processOutbox(ctx context.Context) error {
	events, err := c.outbox.ClaimPending(ctx, c.cfg.BatchSize)
	if err != nil {
		return err
	}
	for _, ev := range events {
		if err := c.handleEvent(ctx, ev); err != nil {
			c.logger.Warn("event handling failed; will retry",
				"event_id", ev.ID, "event_type", ev.EventType, "error", err.Error())
			if err := c.outbox.Fail(ctx, ev.ID, c.cfg.MaxDeliveryAttempts, c.cfg.BaseBackoff); err != nil {
				return err
			}
			metrics.OutboxEventsProcessed.WithLabelValues(ev.EventType, "failed").Inc()
			continue
		}
		if err := c.outbox.Complete(ctx, ev.ID); err != nil {
			return err
		}
		metrics.OutboxEventsProcessed.WithLabelValues(ev.EventType, "processed").Inc()
	}
	return nil
}

func (c *Consumer) handleEvent(ctx context.Context, ev outbox.PendingEvent) error {
	if NotifiableEvents[ev.EventType] && ev.OrganizationID != "" {
		if _, err := c.store.CreateDeliveries(ctx, ev.OrganizationID, ev.ID, ev.EventType); err != nil {
			return fmt.Errorf("create deliveries: %w", err)
		}
	}
	if EvidenceTriggerEvents[ev.EventType] && c.evidence != nil {
		if _, err := c.evidence.Generate(ctx, ev.AggregateID); err != nil {
			// A stale event whose incident no longer exists is not a
			// retryable failure: the evidence cannot ever be generated.
			if errors.KindOf(err) == errors.KindNotFound {
				c.logger.Warn("evidence skipped: incident no longer exists",
					"event_id", ev.ID, "incident_id", ev.AggregateID)
				return nil
			}
			return fmt.Errorf("evidence generation: %w", err)
		}
	}
	return nil
}

// processDeliveries sends due notification deliveries with retry/backoff.
func (c *Consumer) processDeliveries(ctx context.Context) error {
	deliveries, err := c.store.ClaimDueDeliveries(ctx, c.cfg.BatchSize)
	if err != nil {
		return err
	}
	for _, d := range deliveries {
		if err := c.sendDelivery(ctx, d); err != nil {
			c.logger.Warn("delivery send failed", "delivery_id", d.ID, "error", err.Error())
		}
	}
	return nil
}

func (c *Consumer) sendDelivery(ctx context.Context, d Delivery) error {
	channel, err := c.store.ChannelByID(ctx, d.ChannelID)
	if err != nil {
		// Channel deleted: dead-letter so the row stops retrying.
		return c.store.MarkDeadLetter(ctx, d.ID, "channel not found")
	}
	provider, ok := c.providers[channel.Type]
	if !ok {
		return c.store.MarkDeadLetter(ctx, d.ID, "no provider for "+channel.Type)
	}
	msg := Render(d.EventType, d.EventID)
	if err := provider.Send(ctx, channel, msg); err != nil {
		metrics.NotificationFailedTotal.WithLabelValues(channel.Type).Inc()
		if d.Attempt >= c.cfg.MaxDeliveryAttempts {
			return c.store.MarkDeadLetter(ctx, d.ID, err.Error())
		}
		backoff := c.backoff(d.Attempt)
		return c.store.MarkRetry(ctx, d.ID, d.Attempt, c.now().Add(backoff), err.Error())
	}
	metrics.NotificationSentTotal.WithLabelValues(channel.Type).Inc()
	return c.store.MarkSent(ctx, d.ID)
}

func (c *Consumer) backoff(attempt int) time.Duration {
	b := c.cfg.BaseBackoff
	for i := 1; i < attempt; i++ {
		b *= 2
		if b >= c.cfg.MaxBackoff {
			return c.cfg.MaxBackoff
		}
	}
	return b
}
