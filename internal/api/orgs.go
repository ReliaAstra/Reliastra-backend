package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

type createOrgRequest struct {
	Name string `json:"name"`
	Slug string `json:"slug"`
}

func (h *Handlers) listOrganizations(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	memberships, err := h.deps.Orgs.ListForUser(r.Context(), p.UserID)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"organizations": memberships})
}

func (h *Handlers) createOrganization(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req createOrgRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	org, err := h.deps.Orgs.CreateOrganization(r.Context(), p.UserID, req.Name, req.Slug)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, org.ID, p.UserID, "user", "organization.created", "organization", org.ID, nil)
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"organization": org})
}
