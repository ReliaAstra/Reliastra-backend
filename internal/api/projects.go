package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type projectRequest struct {
	Name        string `json:"name"`
	Slug        string `json:"slug"`
	Description string `json:"description"`
}

func (h *Handlers) listProjects(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	orgID := httpapi.OrgID(r.Context())
	projects, err := h.deps.Projects.List(r.Context(), orgID)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"projects": projects})
}

func (h *Handlers) createProject(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	orgID := httpapi.OrgID(r.Context())
	p := httpapi.Principal(r.Context())
	var req projectRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.Name == "" {
		httpapi.WriteError(w, h.log, rid, validationErr("name", "project name is required"))
		return
	}
	project, err := h.deps.Projects.Create(r.Context(), orgID, req.Name, req.Slug, req.Description)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, orgID, p.UserID, "user", "project.created", "project", project.ID, nil)
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"project": project})
}

func (h *Handlers) getProject(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	project, err := h.deps.Projects.ByID(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"project": project})
}

func (h *Handlers) updateProject(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req projectRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	project, err := h.deps.Projects.Update(r.Context(), httpapi.OrgID(r.Context()),
		r.PathValue("id"), req.Name, req.Slug, req.Description)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "project.updated", "project", project.ID, nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"project": project})
}

func (h *Handlers) deleteProject(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Projects.Delete(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, "user", "project.deleted", "project", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}
