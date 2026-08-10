// Package seed creates deterministic development seed data: regions, the
// public vendor catalog, and a demo tenant with services, dependencies,
// relationships and monitors. It is idempotent and safe to re-run. It never
// contains production secrets.
package seed

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/internal/auth"
	"github.com/ReliaAstra/reliastra-backend/internal/organizations"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Run applies the seed data. Requires the migrations to be applied first.
func Run(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config) error {
	if cfg.Env == "production" {
		return fmt.Errorf("seed: refusing to seed a production environment")
	}
	if err := seedRegions(ctx, pool); err != nil {
		return err
	}
	if err := seedVendors(ctx, pool); err != nil {
		return err
	}
	if err := seedPublicMonitors(ctx, pool, cfg); err != nil {
		return err
	}
	return seedDemoTenant(ctx, pool, cfg)
}

// seedRegions inserts the Phase 1 observation regions (data-driven).
func seedRegions(ctx context.Context, pool *pgxpool.Pool) error {
	regions := []struct {
		name, slug, country, provider string
		caps                          []string
	}{
		{"Europe West", "eu-west", "DE", "aws", []string{"http"}},
		{"US East", "us-east", "US", "aws", []string{"http"}},
		{"Asia Southeast", "ap-southeast", "SG", "aws", []string{"http"}},
		{"Africa West", "africa-west", "ZA", "hetzner", []string{"http"}},
	}
	for _, r := range regions {
		caps, _ := json.Marshal(r.caps)
		_, err := pool.Exec(ctx, `INSERT INTO regions (id, name, slug, country, provider, status, capabilities)
			VALUES ($1,$2,$3,$4,$5,'active',$6)
			ON CONFLICT (slug) DO NOTHING`,
			ids.NewUUID(), r.name, r.slug, r.country, r.provider, string(caps))
		if err != nil {
			return fmt.Errorf("seed regions: %w", err)
		}
	}
	return nil
}

// seedVendors inserts the public vendor catalog.
func seedVendors(ctx context.Context, pool *pgxpool.Pool) error {
	vendors := []struct {
		slug, name, provider, category, desc string
	}{
		{"stripe", "Stripe", "stripe", "payment", "Payment infrastructure for the internet."},
		{"cloudflare", "Cloudflare", "cloudflare", "cdn", "Content delivery and edge network."},
		{"auth0", "Auth0", "auth0", "auth", "Identity and access management platform."},
		{"openai", "OpenAI", "openai", "ai", "Artificial intelligence and LLM APIs."},
		{"aws", "AWS", "amazon", "cloud", "Amazon Web Services."},
		{"twilio", "Twilio", "twilio", "email", "Communications APIs (voice, SMS, email)."},
		{"vercel", "Vercel", "vercel", "cloud", "Frontend cloud and edge functions."},
	}
	for _, v := range vendors {
		_, err := pool.Exec(ctx, `INSERT INTO vendors (id, slug, name, provider, category, description, public_enabled)
			VALUES ($1,$2,$3,$4,$5,$6,true)
			ON CONFLICT (slug) DO NOTHING`,
			ids.NewUUID(), v.slug, v.name, v.provider, v.category, v.desc)
		if err != nil {
			return fmt.Errorf("seed vendors: %w", err)
		}
	}
	return nil
}

// seedPublicMonitors creates public monitors for the vendor catalog so the
// tracking pages accumulate observations.
func seedPublicMonitors(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config) error {
	targets := map[string]string{
		"stripe":     "https://status.stripe.com",
		"cloudflare": "https://www.cloudflare.com",
		"auth0":      "https://www.auth0.com",
		"openai":     "https://status.openai.com",
		"aws":        "https://aws.amazon.com",
		"twilio":     "https://www.twilio.com",
		"vercel":     "https://vercel.com",
	}
	// The first active region is used for public monitors.
	var regionID string
	err := pool.QueryRow(ctx, `SELECT id FROM regions WHERE status='active' ORDER BY created_at LIMIT 1`).Scan(&regionID)
	if err != nil {
		return fmt.Errorf("seed public monitors: no active region: %w", err)
	}
	for slug, target := range targets {
		var vendorID string
		if err := pool.QueryRow(ctx, `SELECT id FROM vendors WHERE slug=$1`, slug).Scan(&vendorID); err != nil {
			continue
		}
		httpCfg := map[string]any{
			"url": target, "method": "GET", "expected_status_codes": []int{200},
			"redirect_policy": "follow",
		}
		raw, _ := json.Marshal(httpCfg)
		_, err := pool.Exec(ctx, `INSERT INTO monitors
			(id, vendor_id, name, type, target, configuration, interval_seconds, timeout_seconds,
			 max_attempts, enabled, visibility, status, next_run_at)
			VALUES ($1,$2,$3,'http',$4,$5,300,10,3,true,'public','active', now())
			ON CONFLICT DO NOTHING`,
			ids.NewUUID(), vendorID, "Public "+slug, target, string(raw))
		if err != nil {
			return fmt.Errorf("seed public monitors: %w", err)
		}
		// Assign the region to every public monitor.
		_, err = pool.Exec(ctx, `INSERT INTO monitor_regions (monitor_id, region_id)
			SELECT id, $2 FROM monitors WHERE vendor_id=$1 AND visibility='public'
			ON CONFLICT DO NOTHING`, vendorID, regionID)
		if err != nil {
			return fmt.Errorf("seed public monitor regions: %w", err)
		}
	}
	return nil
}

// seedDemoTenant creates a development user, org, project, services,
// dependencies and monitors.
func seedDemoTenant(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config) error {
	email := "demo@reliastra.dev"
	var userID string
	err := pool.QueryRow(ctx, `SELECT id FROM users WHERE lower(email)=lower($1)`, email).Scan(&userID)
	if err != nil {
		hash, err := auth.HashPassword("demo-password-change-me", auth.DefaultPasswordParams())
		if err != nil {
			return err
		}
		userID = ids.NewUUID()
		if _, err := pool.Exec(ctx, `INSERT INTO users (id, email, password_hash, name)
			VALUES ($1,$2,$3,'Demo User')`, userID, email, hash); err != nil {
			return fmt.Errorf("seed demo user: %w", err)
		}
	}
	var orgID string
	err = pool.QueryRow(ctx, `SELECT id FROM organizations WHERE slug='demo'`).Scan(&orgID)
	if err != nil {
		orgID = ids.NewUUID()
		if _, err := pool.Exec(ctx, `INSERT INTO organizations (id, name, slug, plan)
			VALUES ($1,'Demo Org','demo','professional')`, orgID); err != nil {
			return fmt.Errorf("seed demo org: %w", err)
		}
	}
	if _, err := pool.Exec(ctx, `INSERT INTO organization_members (organization_id, user_id, role)
		VALUES ($1,$2,'owner') ON CONFLICT DO NOTHING`, orgID, userID); err != nil {
		return err
	}

	var projectID string
	err = pool.QueryRow(ctx, `SELECT id FROM projects WHERE slug='checkout' AND organization_id=$1`, orgID).Scan(&projectID)
	if err != nil {
		projectID = ids.NewUUID()
		if _, err := pool.Exec(ctx, `INSERT INTO projects (id, organization_id, name, slug, description)
			VALUES ($1,$2,'Checkout Platform','checkout','Demo checkout platform')`, projectID, orgID); err != nil {
			return fmt.Errorf("seed demo project: %w", err)
		}
	}

	serviceID := upsertNamed(ctx, pool,
		"INSERT INTO services (id, project_id, name, identifier, base_url) VALUES ($1,$2,'Checkout API','checkout-api','https://api.example.com')",
		"SELECT id FROM services WHERE identifier='checkout-api' AND project_id=$1",
		projectID)

	depNames := map[string]string{
		"Stripe": "payment", "Cloudflare": "cdn", "Auth0": "auth", "OpenAI": "ai",
	}
	var serviceDependencyID string
	for name, typ := range depNames {
		var depID string
		err := pool.QueryRow(ctx, `SELECT id FROM dependencies WHERE name=$1 AND project_id=$2`, name, projectID).Scan(&depID)
		if err != nil {
			depID = ids.NewUUID()
			if _, err := pool.Exec(ctx, `INSERT INTO dependencies (id, project_id, name, provider, type, identifier)
				VALUES ($1,$2,$3,$4,$5,$6)`,
				depID, projectID, name, name, typ, name); err != nil {
				return fmt.Errorf("seed dependency %s: %w", name, err)
			}
		}
		criticality := "high"
		if name == "Stripe" || name == "Auth0" {
			criticality = "critical"
		}
		var existing string
		if err := pool.QueryRow(ctx, `SELECT id FROM service_dependencies WHERE service_id=$1 AND dependency_id=$2`,
			serviceID, depID).Scan(&existing); err != nil {
			_, err = pool.Exec(ctx, `INSERT INTO service_dependencies (id, service_id, dependency_id, criticality, description)
				VALUES ($1,$2,$3,$4,$5)`,
				ids.NewUUID(), serviceID, depID, criticality,
				"Seeded relationship between "+name+" and Checkout API")
			if err != nil {
				return fmt.Errorf("seed service dependency: %w", err)
			}
		}
		serviceDependencyID = depID
	}

	// Seed monitors: one for the service and one for each dependency.
	monitorSpecs := []struct {
		name      string
		serviceID string
		depID     string
		target    string
		interval  int
	}{
		{"Checkout API health", serviceID, "", "https://api.example.com/health", 60},
		{"Stripe API health", "", serviceDependencyID, "https://api.stripe.com/v1", 60},
	}
	var regionID string
	_ = pool.QueryRow(ctx, `SELECT id FROM regions WHERE slug='eu-west'`).Scan(&regionID)
	if regionID == "" {
		_ = pool.QueryRow(ctx, `SELECT id FROM regions WHERE status='active' ORDER BY created_at LIMIT 1`).Scan(&regionID)
	}
	for _, ms := range monitorSpecs {
		var existing string
		if err := pool.QueryRow(ctx, `SELECT id FROM monitors WHERE name=$1`, ms.name).Scan(&existing); err != nil {
			cfgJSON, _ := json.Marshal(map[string]any{
				"url": ms.target, "method": "GET", "expected_status_codes": []int{200},
				"redirect_policy": "follow",
			})
			var mid string
			err := pool.QueryRow(ctx, `INSERT INTO monitors
				(id, project_id, organization_id, service_id, dependency_id, name, type, target,
				 configuration, interval_seconds, timeout_seconds, max_attempts, enabled, next_run_at)
				VALUES ($1,$2,$3,$4,$5,$6,'http',$7,$8,$9,10,3,true, now())
				RETURNING id`,
				ids.NewUUID(), projectID, orgID, nullable(ms.serviceID), nullable(ms.depID),
				ms.name, ms.target, string(cfgJSON), ms.interval).Scan(&mid)
			if err != nil {
				return fmt.Errorf("seed monitor %s: %w", ms.name, err)
			}
			if regionID != "" {
				if _, err := pool.Exec(ctx, `INSERT INTO monitor_regions (monitor_id, region_id) VALUES ($1,$2)`,
					mid, regionID); err != nil {
					return err
				}
			}
		}
	}

	// Seed a sample public observation so tracking pages render immediately.
	var stripeMonitorID string
	_ = pool.QueryRow(ctx, `SELECT m.id FROM monitors m JOIN vendors v ON v.id = m.vendor_id
		WHERE v.slug='stripe' LIMIT 1`).Scan(&stripeMonitorID)
	if stripeMonitorID != "" && regionID != "" {
		if _, err := pool.Exec(ctx, `INSERT INTO public_observations
			(id, vendor_id, region_id, monitor_id, observed_at, availability, latency_ms)
			SELECT $1, id, $2, $3, now(), true, 120
			FROM vendors WHERE slug='stripe'
			ON CONFLICT DO NOTHING`,
			ids.NewUUID(), regionID, stripeMonitorID); err != nil {
			return fmt.Errorf("seed public observation: %w", err)
		}
	}

	_ = organizations.RoleOwner
	_ = time.Now
	return nil
}

func upsertNamed(ctx context.Context, pool *pgxpool.Pool, insertSQL, selectSQL string, projectID string) string {
	var id string
	if err := pool.QueryRow(ctx, selectSQL, projectID).Scan(&id); err == nil {
		return id
	}
	id = ids.NewUUID()
	// insertSQL uses $1 for the id and $2 for project id.
	if _, err := pool.Exec(ctx, insertSQL, id, projectID); err != nil {
		return ""
	}
	return id
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}
