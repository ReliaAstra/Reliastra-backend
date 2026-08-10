package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/auth"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type apiKeyRequest struct {
	Name   string          `json:"name"`
	Scopes []auth.APIScope `json:"scopes"`
}

func (h *Handlers) listAPIKeys(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	keys, err := h.deps.Auth.ListAPIKeys(r.Context(), httpapi.Principal(r.Context()))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"api_keys": keys})
}

func (h *Handlers) createAPIKey(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req apiKeyRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.Name == "" {
		httpapi.WriteError(w, h.log, rid, validationErr("name", "API key name is required"))
		return
	}
	if len(req.Scopes) == 0 {
		req.Scopes = []auth.APIScope{auth.ScopeMonitorRead, auth.ScopeIncidentRead, auth.ScopeEvidenceRead}
	}
	key, err := h.deps.Auth.CreateAPIKey(r.Context(), p, req.Name, req.Scopes)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, p.OrganizationID, p.UserID, p.AuthMethod, "api_key.created", "api_key", key.ID, nil)
	// The secret is returned exactly once.
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"api_key": key})
}

func (h *Handlers) revokeAPIKey(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Auth.RevokeAPIKey(r.Context(), p, r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, p.OrganizationID, p.UserID, p.AuthMethod, "api_key.revoked", "api_key", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"revoked": true})
}
