package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

// generateEvidence triggers asynchronous evidence generation for an incident.
// Idempotency is provided both by the Idempotency-Key header and by the
// evidence engine's finalized-record deduplication.
func (h *Handlers) generateEvidence(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	orgID := httpapi.OrgID(r.Context())

	// The incident must belong to the org.
	inc, err := h.deps.Incidents.ByID(r.Context(), orgID, r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if err := p.RequireScope("evidence:write"); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	// Enqueue a generation request through the outbox (async, durable).
	evID := r.Header.Get("Idempotency-Key")
	if err := h.deps.Evidence.Enqueue(r.Context(), inc, evID); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, orgID, p.UserID, p.AuthMethod, "evidence.requested", "incident", inc.ID, nil)
	httpapi.WriteData(w, rid, http.StatusAccepted, map[string]any{
		"status":     "queued",
		"incident_id": inc.ID,
		"number":     inc.Number,
	})
}

func (h *Handlers) incidentEvidence(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	orgID := httpapi.OrgID(r.Context())
	inc, err := h.deps.Incidents.ByID(r.Context(), orgID, r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	records, err := h.deps.EvStore.ListForIncident(r.Context(), orgID, inc.ID)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"evidence": records})
}

func (h *Handlers) getEvidence(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	rec, err := h.deps.EvStore.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"evidence": rec})
}

func (h *Handlers) verifyEvidence(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	rec, err := h.deps.EvStore.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	result, err := h.deps.Evidence.Verify(r.Context(), rec)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	status := http.StatusOK
	if !result.Valid {
		status = http.StatusUnprocessableEntity
	}
	httpapi.WriteData(w, rid, status, map[string]any{"verification": result})
}

func (h *Handlers) downloadEvidence(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	rec, err := h.deps.EvStore.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	format := r.URL.Query().Get("format")
	if format != "pdf" {
		format = "json"
	}
	data, contentType, err := h.deps.Evidence.Download(r.Context(), rec, format)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, errors.Unavailable("evidence_unavailable", "evidence artifact is not available"))
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Disposition", "attachment; filename=\""+rec.ID+"."+format+"\"")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}


