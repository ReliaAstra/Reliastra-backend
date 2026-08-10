package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type serviceRequest struct {
	ProjectID  string `json:"project_id"`
	Name       string `json:"name"`
	Identifier string `json:"identifier"`
	BaseURL    string `json:"base_url"`
	Status     string `json:"status"`
}

func (h *Handlers) listServices(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	services, err := h.deps.Services.List(r.Context(), httpapi.OrgID(r.Context()), r.URL.Query().Get("project_id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"services": services})
}

func (h *Handlers) createService(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req serviceRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.ProjectID == "" || req.Name == "" {
		httpapi.WriteError(w, h.log, rid, validationErr("service", "project_id and name are required"))
		return
	}
	svc, err := h.deps.Services.Create(r.Context(), httpapi.OrgID(r.Context()),
		req.ProjectID, req.Name, req.Identifier, req.BaseURL)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "service.created", "service", svc.ID, nil)
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"service": svc})
}

func (h *Handlers) getService(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	svc, err := h.deps.Services.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	links, _ := h.deps.Deps.ListForService(r.Context(), httpapi.OrgID(r.Context()), svc.ID)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{
		"service":           svc,
		"service_dependencies": links,
	})
}

func (h *Handlers) updateService(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req serviceRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	svc, err := h.deps.Services.Update(r.Context(), httpapi.OrgID(r.Context()),
		r.PathValue("id"), req.Name, req.Identifier, req.BaseURL, req.Status)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "service.updated", "service", svc.ID, nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"service": svc})
}

func (h *Handlers) deleteService(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Services.Delete(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "service.deleted", "service", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}
