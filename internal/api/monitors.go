package api

import (
	"encoding/json"
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/monitors"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type monitorRequest struct {
	ProjectID       string          `json:"project_id"`
	ServiceID       string          `json:"service_id"`
	DependencyID    string          `json:"dependency_id"`
	Name            string          `json:"name"`
	Type            string          `json:"type"`
	Target          string          `json:"target"`
	Configuration   json.RawMessage `json:"configuration"`
	IntervalSeconds int             `json:"interval_seconds"`
	TimeoutSeconds  int             `json:"timeout_seconds"`
	MaxAttempts     int             `json:"max_attempts"`
	RegionIDs       []string        `json:"region_ids"`
	Enabled         *bool           `json:"enabled"`
}

func (h *Handlers) listMonitors(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	var enabled *bool
	if v := r.URL.Query().Get("enabled"); v == "true" {
		t := true
		enabled = &t
	} else if v == "false" {
		f := false
		enabled = &f
	}
	monitors, err := h.deps.Monitors.List(r.Context(), httpapi.OrgID(r.Context()),
		r.URL.Query().Get("project_id"), enabled)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"monitors": monitors})
}

func (h *Handlers) createMonitor(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req monitorRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	enabled := true
	if req.Enabled != nil {
		enabled = *req.Enabled
	}
	if req.IntervalSeconds == 0 {
		req.IntervalSeconds = 60
	}
	if req.TimeoutSeconds == 0 {
		req.TimeoutSeconds = 10
	}
	if req.MaxAttempts == 0 {
		req.MaxAttempts = 3
	}

	// Extract secrets (headers/body) from the configuration before storing.
	// The stored configuration is redacted; secrets live encrypted elsewhere.
	redactedCfg, secrets, secretBody, err := monitors.ExtractSecrets(req.Configuration)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}

	monitor, err := h.deps.Monitors.Create(r.Context(), httpapi.OrgID(r.Context()), monitors.CreateInput{
		ProjectID:       req.ProjectID,
		ServiceID:       req.ServiceID,
		DependencyID:    req.DependencyID,
		Name:            req.Name,
		Type:            req.Type,
		Target:          req.Target,
		IntervalSeconds: req.IntervalSeconds,
		TimeoutSeconds:  req.TimeoutSeconds,
		MaxAttempts:     req.MaxAttempts,
		RegionIDs:       req.RegionIDs,
		Enabled:         enabled,
		Configuration:   redactedCfg,
		Secrets:         secrets,
		SecretBody:      secretBody,
	})
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "monitor.created", "monitor", monitor.ID, nil)
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"monitor": monitor})
}

func (h *Handlers) getMonitor(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	m, err := h.deps.Monitors.Get(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	regions, _ := h.deps.Monitors.Regions(r.Context(), m.ID)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"monitor": m, "region_ids": regions})
}

func (h *Handlers) updateMonitor(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req monitorRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	in := monitors.UpdateInput{}
	if req.Name != "" {
		in.Name = &req.Name
	}
	if req.Target != "" {
		in.Target = &req.Target
	}
	if len(req.Configuration) > 0 {
		redactedCfg, secrets, secretBody, err := monitors.ExtractSecrets(req.Configuration)
		if err != nil {
			httpapi.WriteError(w, h.log, rid, err)
			return
		}
		in.Configuration = redactedCfg
		in.Secrets = secrets
		in.SecretBody = secretBody
	}
	if req.IntervalSeconds != 0 {
		in.IntervalSeconds = &req.IntervalSeconds
	}
	if req.TimeoutSeconds != 0 {
		in.TimeoutSeconds = &req.TimeoutSeconds
	}
	if req.MaxAttempts != 0 {
		in.MaxAttempts = &req.MaxAttempts
	}
	if req.Enabled != nil {
		in.Enabled = req.Enabled
	}
	if req.RegionIDs != nil {
		in.RegionIDs = req.RegionIDs
	}
	m, err := h.deps.Monitors.Update(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"), in)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "monitor.updated", "monitor", m.ID, nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"monitor": m})
}

func (h *Handlers) deleteMonitor(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Monitors.Delete(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "monitor.deleted", "monitor", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}
