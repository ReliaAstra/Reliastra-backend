package api

import (
	"encoding/json"
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type dependencyRequest struct {
	ProjectID  string          `json:"project_id"`
	Name       string          `json:"name"`
	Provider   string          `json:"provider"`
	Type       string          `json:"type"`
	Identifier string          `json:"identifier"`
	Metadata   map[string]any  `json:"metadata"`
}

func (h *Handlers) listDependencies(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	deps, err := h.deps.Deps.List(r.Context(), httpapi.OrgID(r.Context()), r.URL.Query().Get("project_id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"dependencies": deps})
}

func (h *Handlers) createDependency(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req dependencyRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.ProjectID == "" || req.Name == "" {
		httpapi.WriteError(w, h.log, rid, validationErr("dependency", "project_id and name are required"))
		return
	}
	if req.Type == "" {
		req.Type = "api"
	}
	dep, err := h.deps.Deps.Create(r.Context(), httpapi.OrgID(r.Context()),
		req.ProjectID, req.Name, req.Provider, req.Type, req.Identifier, req.Metadata)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "dependency.created", "dependency", dep.ID, nil)
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"dependency": dep})
}

func (h *Handlers) getDependency(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	dep, err := h.deps.Deps.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"dependency": dep})
}

func (h *Handlers) deleteDependency(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Deps.Delete(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "dependency.deleted", "dependency", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}

type linkRequest struct {
	DependencyID string `json:"dependency_id"`
	Criticality  string `json:"criticality"`
	Description  string `json:"description"`
}

func (h *Handlers) linkDependency(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req linkRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.DependencyID == "" {
		httpapi.WriteError(w, h.log, rid, validationErr("link", "dependency_id is required"))
		return
	}
	if req.Criticality == "" {
		req.Criticality = "medium"
	}
	link, err := h.deps.Deps.Link(r.Context(), httpapi.OrgID(r.Context()),
		r.PathValue("id"), req.DependencyID, req.Criticality, req.Description)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user",
		"service_dependency.created", "service_dependency", link.ID, map[string]any{"dependency_id": req.DependencyID})
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"service_dependency": link})
}

func (h *Handlers) unlinkDependency(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Deps.Unlink(r.Context(), httpapi.OrgID(r.Context()),
		r.PathValue("id"), r.PathValue("dependencyID")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user",
		"service_dependency.deleted", "service_dependency", r.PathValue("dependencyID"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}

var _ = json.Marshal
