package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

// healthLive reports process liveness. It deliberately does not touch the
// database: an orchestrator must never kill a process just because a
// dependency is down (that would make recovery worse).
func (h *Handlers) healthLive(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	st := h.deps.Checker.Live()
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"status": "ok", "live": st.Live})
}

// healthReady probes required dependencies (PostgreSQL, Redis, object store).
func (h *Handlers) healthReady(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	st := h.deps.Checker.Ready(r.Context())
	status := http.StatusOK
	if !st.Ready {
		status = http.StatusServiceUnavailable
	}
	httpapi.WriteData(w, rid, status, map[string]any{"status": map[bool]string{true: "ok", false: "unavailable"}[st.Ready], "ready": st.Ready, "checks": st.Checks})
}
