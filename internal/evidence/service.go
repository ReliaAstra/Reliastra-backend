package evidence

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/checks"
	"github.com/ReliaAstra/reliastra-backend/internal/incidents"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/objectstore"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/outbox"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
	"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// Service generates, stores and verifies evidence artifacts.
type Service struct {
	store         *Store
	gatherer      *Gatherer
	incidents     *incidents.Store
	observations  *checks.ObservationStore
	objects       objectstore.Store
	outbox        *outbox.Store
	cfg           config.EvidenceConfig
	now           func() time.Time
}

// NewService builds the evidence service.
func NewService(store *Store, gatherer *Gatherer, inc *incidents.Store,
	obs *checks.ObservationStore, objects objectstore.Store, outbox *outbox.Store,
	cfg config.EvidenceConfig) *Service {
	return &Service{
		store: store, gatherer: gatherer, incidents: inc, observations: obs,
		objects: objects, outbox: outbox, cfg: cfg, now: time.Now,
	}
}

// Enqueue writes an evidence.requested outbox event so generation happens
// asynchronously. When an Idempotency-Key is supplied, the outbox event id is
// derived from it: duplicate requests collapse onto the same event (ON
// CONFLICT DO NOTHING), and finalized records are never regenerated.
func (s *Service) Enqueue(ctx context.Context, inc *incidents.Incident, idempotencyKey string) error {
	eventID := ids.NewUUID()
	if idempotencyKey != "" {
		eventID = deterministicID(idempotencyKey)
	}
	ev := outbox.Event{
		ID: eventID, EventType: "evidence.requested", AggregateType: "incident",
		AggregateID: inc.ID, OrganizationID: inc.OrganizationID,
		Payload: map[string]any{"incident_id": inc.ID, "number": inc.Number},
	}
	// Idempotent insert: a duplicate request is a no-op.
	_, err := s.outbox.WriteOnce(ctx, ev)
	return err
}

// deterministicID derives a stable UUID from an idempotency key.
func deterministicID(key string) string {
	sum := sha256.Sum256([]byte("evidence:" + key))
	sum[6] = (sum[6] & 0x0f) | 0x50 // version 5
	sum[8] = (sum[8] & 0x3f) | 0x80 // variant
	var b [16]byte
	copy(b[:], sum[:16])
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func mustJSON(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return b
}

// Generate produces a new evidence version for an incident (async consumer).
// It is idempotent: when a finalized version already exists, the existing
// record is returned and no duplicate artifact is written.
func (s *Service) Generate(ctx context.Context, incidentID string) (*EvidenceRecord, error) {
	if !s.cfg.Enabled {
		return nil, nil
	}
	inc, err := s.incidents.ByIDAny(ctx, incidentID)
	if err != nil {
		return nil, err
	}

	// Idempotency: never regenerate a finalized artifact.
	latest, err := s.store.LatestForIncident(ctx, incidentID)
	if err == nil && latest.Status == StatusFinalized {
		return latest, nil
	}

	rec, err := s.store.BeginGeneration(ctx, incidentID, s.cfg.MethodologyVersion)
	if err != nil {
		return nil, err
	}

	pkg, err := s.gatherer.Build(ctx, inc, rec, s.cfg.MethodologyVersion,
		s.cfg.CorrelationVersion, s.cfg.ScoringConfigVersion, s.cfg.MaxObservationFetch)
	if err != nil {
		s.store.MarkFailed(ctx, rec, err.Error()) //nolint:errcheck
		metrics.EvidenceGenerationFailuresTotal.Inc()
		return nil, fmt.Errorf("evidence: build: %w", err)
	}
	hash, canonical, err := HashPackage(pkg)
	if err != nil {
		s.store.MarkFailed(ctx, rec, err.Error()) //nolint:errcheck
		metrics.EvidenceGenerationFailuresTotal.Inc()
		return nil, err
	}

	key := fmt.Sprintf("%s/%s/%03d.json", s.cfg.StoragePrefix, incidentID, rec.Version)
	if err := s.objects.Put(ctx, key, bytes.NewReader(canonical), int64(len(canonical)), "application/json"); err != nil {
		s.store.MarkFailed(ctx, rec, err.Error()) //nolint:errcheck
		metrics.EvidenceGenerationFailuresTotal.Inc()
		return nil, fmt.Errorf("evidence: store json: %w", err)
	}

	if s.cfg.PDFEnabled {
		pdfBytes, err := GeneratePDF(pkg)
		if err == nil {
			pdfKey := fmt.Sprintf("%s/%s/%03d.pdf", s.cfg.StoragePrefix, incidentID, rec.Version)
			if err := s.objects.Put(ctx, pdfKey, bytes.NewReader(pdfBytes), int64(len(pdfBytes)), "application/pdf"); err != nil {
				s.store.MarkFailed(ctx, rec, err.Error()) //nolint:errcheck
				metrics.EvidenceGenerationFailuresTotal.Inc()
				return nil, fmt.Errorf("evidence: store pdf: %w", err)
			}
		}
	}

	if err := s.store.Finalize(ctx, rec, hash, key, int64(len(canonical))); err != nil {
		return nil, err
	}

	// Event for notification consumers (evidence.generated).
	ev := outbox.Event{
		ID: ids.NewUUID(), EventType: "evidence.generated", AggregateType: "incident",
		AggregateID: incidentID, OrganizationID: inc.OrganizationID,
		Payload: map[string]any{
			"incident_id": incidentID, "evidence_id": rec.ID, "version": rec.Version,
			"hash": hash, "status": "finalized",
		},
	}
	if err := s.outbox.Write(ctx, nil, ev); err != nil {
		return rec, err
	}
	metrics.EvidenceGeneratedTotal.Inc()
	return rec, nil
}

// VerificationResult is the outcome of integrity verification.
type VerificationResult struct {
	Valid            bool     `json:"valid"`
	Checks           []string `json:"checks"`
	Failures         []string `json:"failures,omitempty"`
	EvidenceID       string   `json:"evidence_id"`
	Version          int      `json:"version"`
	Hash             string   `json:"hash"`
	HashAlgorithm    string   `json:"hash_algorithm"`
}

// Verify checks artifact existence, digest, version and status.
func (s *Service) Verify(ctx context.Context, rec *EvidenceRecord) (*VerificationResult, error) {
	res := &VerificationResult{
		EvidenceID: rec.ID, Version: rec.Version, Hash: rec.Hash,
		HashAlgorithm: rec.HashAlgorithm,
	}
	ok := func(name string) { res.Checks = append(res.Checks, name) }
	bad := func(name, detail string) {
		res.Failures = append(res.Failures, name+": "+detail)
	}

	if rec.Status != StatusFinalized {
		bad("status", "evidence is not finalized (status="+rec.Status+")")
	} else {
		ok("status finalized")
	}
	obj, err := s.objects.Stat(ctx, rec.StorageKey)
	if err != nil {
		bad("artifact_exists", "object not found in storage")
	} else {
		ok("artifact exists ("+obj.Key+")")
		rc, err := s.objects.Get(ctx, rec.StorageKey)
		if err != nil {
			bad("artifact_readable", err.Error())
		} else {
			data, _ := io.ReadAll(io.LimitReader(rc, 64<<20))
			rc.Close()
			if VerifyBytes(data, rec.Hash) {
				ok("hash matches (sha256)")
			} else {
				bad("hash_matches", "SHA-256 digest does not match the recorded hash")
			}
		}
	}
	if rec.HashAlgorithm != "sha256" {
		bad("hash_algorithm", "unsupported algorithm "+rec.HashAlgorithm)
	} else {
		ok("hash algorithm sha256")
	}
	res.Valid = len(res.Failures) == 0
	return res, nil
}

// Download returns the artifact bytes for a record (JSON or PDF).
func (s *Service) Download(ctx context.Context, rec *EvidenceRecord, format string) ([]byte, string, error) {
	key := rec.StorageKey
	contentType := "application/json"
	if format == "pdf" {
		key = pdfKey(rec.StorageKey)
		contentType = "application/pdf"
	}
	rc, err := s.objects.Get(ctx, key)
	if err != nil {
		return nil, "", err
	}
	defer rc.Close()
	data, err := io.ReadAll(io.LimitReader(rc, 64<<20))
	if err != nil {
		return nil, "", err
	}
	return data, contentType, nil
}

func pdfKey(jsonKey string) string {
	return jsonKey[:len(jsonKey)-len(".json")] + ".pdf"
}
