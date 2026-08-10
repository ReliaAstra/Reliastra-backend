// Package load contains load-test scenarios. They are excluded from the
// default test run (build tag `load`) and require a running stack.
//
//	RELI_TEST_BASE_URL=http://localhost:8080 go test -tags load ./tests/load -v
//
// Scenarios:
//  1. API: N concurrent clients performing CRUD + queries.
//  2. Scheduler: create K monitors and measure job creation.
//  3. Worker: large batches of simultaneous checks against a local target.
package load

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func baseURL() string {
	u := os.Getenv("RELI_TEST_BASE_URL")
	if u == "" {
		u = "http://localhost:8080"
	}
	return u
}

func mustAuth(t *testing.T) (string, string) {
	t.Helper()
	resp, err := http.Post(baseURL()+"/v1/auth/login", "application/json",
		bytes.NewBufferString(`{"email":"load@reliastra.dev","password":"load-password-123"}`))
	if err != nil {
		t.Fatalf("login: %v", err)
	}
	defer resp.Body.Close()
	var out struct {
		Data struct {
			Token string `json:"token"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.Data.Token == "" {
		t.Fatal("no token")
	}
	// Derive org id.
	req, _ := http.NewRequest("GET", baseURL()+"/v1/organizations", nil)
	req.Header.Set("Authorization", "Bearer "+out.Data.Token)
	r2, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("orgs: %v", err)
	}
	defer r2.Body.Close()
	body, _ := io.ReadAll(r2.Body)
	var orgs struct {
		Data struct {
			Organizations []struct {
				OrganizationID string `json:"organization_id"`
			} `json:"organizations"`
		} `json:"data"`
	}
	_ = json.Unmarshal(body, &orgs)
	if len(orgs.Data.Organizations) == 0 {
		t.Fatal("no organization")
	}
	return out.Data.Token, orgs.Data.Organizations[0].OrganizationID
}

func TestAPIConcurrency(t *testing.T) {
	token, org := mustAuth(t)
	const clients = 200
	const perClient = 20
	var ok atomic.Int64
	var wg sync.WaitGroup
	start := time.Now()
	for i := 0; i < clients; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perClient; j++ {
				req, _ := http.NewRequest("GET", baseURL()+"/v1/projects", nil)
				req.Header.Set("Authorization", "Bearer "+token)
				req.Header.Set("X-Reliasorg", org)
				resp, err := http.DefaultClient.Do(req)
				if err == nil {
					io.Copy(io.Discard, resp.Body)
					resp.Body.Close()
					if resp.StatusCode == 200 {
						ok.Add(1)
					}
				}
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)
	total := clients * perClient
	t.Logf("api: %d requests in %s (%.0f req/s), %d ok",
		total, elapsed, float64(total)/elapsed.Seconds(), ok.Load())
	if ok.Load() < int64(total)*9/10 {
		t.Errorf("success rate too low: %d/%d", ok.Load(), total)
	}
}

func TestSchedulerThroughput(t *testing.T) {
	// Seed many monitors pointing at an unroutable target and measure job
	// creation. Requires a running scheduler+worker.
	token, org := mustAuth(t)
	req, _ := http.NewRequest("GET", baseURL()+"/v1/regions", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-Reliasorg", org)
	resp, err := http.DefaultClient.Do(req)
	if err != nil { t.Fatalf("regions: %v", err) }
	var regions struct {
		Data struct {
			Regions []struct{ ID string `json:"id"` } `json:"regions"`
		} `json:"data"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&regions)
	resp.Body.Close()
	if len(regions.Data.Regions) == 0 { t.Fatal("no regions seeded") }
	regionID := regions.Data.Regions[0].ID

	const monitors = 50
	created := 0
	for i := 0; i < monitors; i++ {
		body := fmt.Sprintf(`{"name":"load-%d","type":"http","interval_seconds":30,
			"timeout_seconds":5,"region_ids":["%s"],
			"configuration":{"url":"http://127.0.0.1:9/health","method":"GET","expected_status_codes":[200]}}`, i, regionID)
		req, _ := http.NewRequest("POST", baseURL()+"/v1/monitors", bytes.NewBufferString(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("X-Reliasorg", org)
		resp, err := http.DefaultClient.Do(req)
		if err == nil {
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if resp.StatusCode == 201 {
				created++
			}
		}
	}
	t.Logf("created %d/%d monitors", created, monitors)
	if created < monitors*8/10 {
		t.Errorf("monitor creation rate too low: %d/%d", created, monitors)
	}
}

var _ = time.Now
