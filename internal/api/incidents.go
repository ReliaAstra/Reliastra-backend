package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

func (h *Handlers) listIncidents(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := parseInt(v); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}
	offset := 0
	if v := r.URL.Query().Get("offset"); v != "" {
		if n, err := parseInt(v); err == nil && n >= 0 {
			offset = n
		}
	}
	incidents, err := h.deps.Incidents.List(r.Context(), httpapi.OrgID(r.Context()),
		r.URL.Query().Get("project_id"), r.URL.Query().Get("status"), limit, offset)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"incidents": incidents})
}

func (h *Handlers) getIncident(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	id := r.PathValue("id")
	// Support lookup by INC-... number or UUID.
	inc, err := h.deps.Incidents.ByID(r.Context(), httpapi.OrgID(r.Context()), id)
	if err != nil && errors.KindOf(err) == errors.KindNotFound {
		inc, err = h.deps.Incidents.ByNumber(r.Context(), httpapi.OrgID(r.Context()), id)
	}
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	events, _ := h.deps.Incidents.ListEvents(r.Context(), inc.ID)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{
		"incident": inc,
		"events":   events,
	})
}
