package api

import (
	"context"
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/audit"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
)

// auditAction records an audit entry from a request. It is best-effort: a
// failed audit write must never fail the user-facing operation.
func (h *Handlers) auditAction(ctx context.Context, r *http.Request, orgID, actorID, actorType, action, resourceType, resourceID string, meta map[string]any) {
	if h.deps.Audit == nil || orgID == "" {
		return
	}
	rec := audit.Record{
		OrganizationID: orgID,
		ActorID:        actorID,
		ActorType:      actorType,
		Action:         action,
		ResourceType:   resourceType,
		ResourceID:     resourceID,
		Metadata:       meta,
		IPAddress:      httpapi.ClientIP(r, h.deps.Cfg.HTTP.TrustedProxyHeaders),
		UserAgent:      r.UserAgent(),
	}
	if err := h.deps.Audit.Write(ctx, rec); err != nil {
		h.log.Warn("audit write failed", "action", action, "error", err.Error())
	}
}
