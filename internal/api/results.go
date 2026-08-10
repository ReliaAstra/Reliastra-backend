package api

import (
	"net/http"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

func (h *Handlers) monitorResults(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	// Tenant check first: the monitor must belong to the org.
	m, err := h.deps.Monitors.Get(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := parseInt(v); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}
	var since time.Time
	if v := r.URL.Query().Get("since"); v != "" {
		if t, err := time.Parse(time.RFC3339, v); err == nil {
			since = t
		}
	}
	results, err := h.deps.Results.ListForMonitor(r.Context(), m.ID, limit, since)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"results": results})
}
