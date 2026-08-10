package api

import (
	"net/http"

	"github.com/ReliaAstra/reliastra-backend/internal/auth"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

type registerRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

func (h *Handlers) register(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	var req registerRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	user, err := h.deps.Auth.Register(r.Context(), req.Email, req.Password, req.Name)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusCreated, map[string]any{"user": user})
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (h *Handlers) login(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	var req loginRequest
	if err := httpapi.DecodeJSON(w, r, &req, rid); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	token, user, err := h.deps.Auth.Login(r.Context(), req.Email, req.Password,
		httpapi.ClientIP(r, h.deps.Cfg.HTTP.TrustedProxyHeaders), r.UserAgent())
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{
		"token": token,
		"token_type": "bearer",
		"user":  user,
	})
}

func (h *Handlers) logout(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	token := auth.ParseBearer(r.Header.Get("Authorization"))
	if token == "" {
		httpapi.WriteError(w, h.log, rid, errors.Authentication("missing_credentials", "authentication required"))
		return
	}
	if err := h.deps.Auth.Logout(r.Context(), token); err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"logged_out": true})
}

func (h *Handlers) me(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	p := httpapi.Principal(r.Context())
	user, err := h.deps.Auth.Me(r.Context(), p.UserID)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"user": user})
}
