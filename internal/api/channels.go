package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

type channelRequest struct {
	ID      string            `json:"id,omitempty"`
	Type    string            `json:"type"`
	Name    string            `json:"name"`
	Enabled *bool             `json:"enabled,omitempty"`
	Config  map[string]string `json:"config"`
}

func (h *Handlers) listChannels(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	channels, err := h.deps.Channels.ListChannels(r.Context(), httpapi.OrgID(r.Context()))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"channels": channels})
}

func (h *Handlers) createChannel(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	var req channelRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if req.Type != "email" && req.Type != "slack" {
		httpapi.WriteError(w, h.log, rid, errors.Validation("invalid_type", "channel type must be email or slack", nil))
		return
	}
	enabled := true
	if req.Enabled != nil {
		enabled = *req.Enabled
	}
	channel, err := h.deps.Channels.UpsertChannel(r.Context(), httpapi.OrgID(r.Context()),
		req.ID, req.Type, req.Name, enabled, req.Config)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, p.AuthMethod, "notification_channel.upserted", "channel", channel.ID, nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"channel": channel})
}

func (h *Handlers) deleteChannel(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	if err := h.deps.Channels.DeleteChannel(r.Context(), httpapi.OrgID(r.Context()), r.PathValue("id")); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	h.auditAction(r.Context(), r, httpapi.OrgID(r.Context()), p.UserID, p.AuthMethod, "notification_channel.deleted", "channel", r.PathValue("id"), nil)
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"deleted": true})
}
