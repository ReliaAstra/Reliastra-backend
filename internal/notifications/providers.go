package notifications

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/smtp"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
)

// Provider delivers a Message to a channel.
type Provider interface {
	Type() string
	// Send delivers the message; returning an error triggers retry/backoff.
	Send(ctx context.Context, channel *Channel, msg Message) error
}

// EmailProvider sends via SMTP (STARTTLS when available).
type EmailProvider struct {
	cfg config.SMTPConfig
}

// NewEmailProvider builds the email provider.
func NewEmailProvider(cfg config.SMTPConfig) *EmailProvider { return &EmailProvider{cfg: cfg} }

// Type implements Provider.
func (p *EmailProvider) Type() string { return ChannelEmail }

// Send implements Provider. The channel config carries the recipient ("to").
func (p *EmailProvider) Send(ctx context.Context, channel *Channel, msg Message) error {
	if !p.cfg.Enabled || p.cfg.Host == "" {
		return fmt.Errorf("email delivery is not configured")
	}
	to := channel.Config["to"]
	if to == "" {
		return fmt.Errorf("email channel has no recipient")
	}
	body := "From: " + p.cfg.From + "\r\n" +
		"To: " + to + "\r\n" +
		"Subject: " + msg.Subject + "\r\n" +
		"MIME-Version: 1.0\r\n" +
		"Content-Type: text/plain; charset=UTF-8\r\n\r\n" +
		msg.Text

	addr := fmt.Sprintf("%s:%d", p.cfg.Host, p.cfg.Port)
	ctxTimeout := p.cfg.Timeout
	if ctxTimeout <= 0 {
		ctxTimeout = 10 * time.Second
	}
	callCtx, cancel := context.WithTimeout(ctx, ctxTimeout)
	defer cancel()

	// Dial with context; upgrade to TLS when supported.
	conn, err := dialSMTP(callCtx, addr)
	if err != nil {
		return err
	}
	host := p.cfg.Host
	client, err := smtp.NewClient(conn, host)
	if err != nil {
		conn.Close()
		return err
	}
	defer client.Close()

	if ok, _ := client.Extension("STARTTLS"); ok {
		tlsCfg := &tls.Config{ServerName: host, MinVersion: tls.VersionTLS12}
		if err := client.StartTLS(tlsCfg); err != nil {
			return fmt.Errorf("smtp starttls: %w", err)
		}
	}
	if p.cfg.Username != "" {
		auth := smtp.PlainAuth("", p.cfg.Username, p.cfg.Password, host)
		if err := client.Auth(auth); err != nil {
			return fmt.Errorf("smtp auth: %w", err)
		}
	}
	if err := client.Mail(p.cfg.From); err != nil {
		return fmt.Errorf("smtp mail from: %w", err)
	}
	if err := client.Rcpt(to); err != nil {
		return fmt.Errorf("smtp rcpt: %w", err)
	}
	w, err := client.Data()
	if err != nil {
		return fmt.Errorf("smtp data: %w", err)
	}
	if _, err := w.Write([]byte(body)); err != nil {
		w.Close()
		return fmt.Errorf("smtp write: %w", err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("smtp write close: %w", err)
	}
	return client.Quit()
}

func dialSMTP(ctx context.Context, addr string) (net.Conn, error) {
	d := net.Dialer{Timeout: 10 * time.Second}
	return d.DialContext(ctx, "tcp", addr)
}

// SlackProvider posts messages to a Slack Incoming Webhook.
type SlackProvider struct {
	cfg    config.SlackConfig
	client *http.Client
}

// NewSlackProvider builds the Slack provider.
func NewSlackProvider(cfg config.SlackConfig) *SlackProvider {
	return &SlackProvider{
		cfg: cfg,
		client: &http.Client{
			Timeout: cfg.Timeout,
			Transport: &http.Transport{
				Proxy:                 http.ProxyFromEnvironment,
				TLSHandshakeTimeout:   5 * time.Second,
				ResponseHeaderTimeout: 5 * time.Second,
				DisableKeepAlives:     true,
			},
		},
	}
}

// Type implements Provider.
func (p *SlackProvider) Type() string { return ChannelSlack }

// Send implements Provider. The channel config carries the webhook URL.
func (p *SlackProvider) Send(ctx context.Context, channel *Channel, msg Message) error {
	if !p.cfg.Enabled {
		return fmt.Errorf("slack delivery is not configured")
	}
	webhook := channel.Config["webhook_url"]
	if webhook == "" {
		return fmt.Errorf("slack channel has no webhook_url")
	}
	text := msg.Markdown
	if text == "" {
		text = msg.Text
	}
	payload, _ := json.Marshal(map[string]any{
		"text":        "*" + msg.Subject + "*\n" + text,
		"unfurl_links": false,
	})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, webhook, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := p.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("slack webhook returned status %d", resp.StatusCode)
	}
	return nil
}
