package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

func (h *Handlers) listAuditLogs(w http.ResponseWriter, r *http.Request) {
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
	records, err := h.deps.Audit.List(r.Context(), httpapi.OrgID(r.Context()), limit, offset)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"audit_logs": records})
}
