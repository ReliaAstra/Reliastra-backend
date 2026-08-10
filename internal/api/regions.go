package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

func (h *Handlers) listRegions(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	regions, err := h.deps.Regions.Active(r.Context())
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"regions": regions})
}
