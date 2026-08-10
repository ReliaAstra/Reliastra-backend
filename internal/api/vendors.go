package api

import (
	"net/http"
	"time"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/httpapi"
	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
)

// Public vendor tracking endpoints. These never return customer data: only
// the vendor catalog and aggregate public observations.

func (h *Handlers) listVendors(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	vendors, err := h.deps.Vendors.ListVendors(r.Context())
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"vendors": vendors})
}

func (h *Handlers) getVendor(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	v, err := h.deps.Vendors.VendorBySlug(r.Context(), r.PathValue("slug"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if !v.PublicEnabled {
		httpapi.WriteError(w, h.log, rid, errors.NotFound("vendor_not_found", "vendor not found"))
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"vendor": v})
}

func (h *Handlers) vendorStatus(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	v, err := h.deps.Vendors.VendorBySlug(r.Context(), r.PathValue("slug"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if !v.PublicEnabled {
		httpapi.WriteError(w, h.log, rid, errors.NotFound("vendor_not_found", "vendor not found"))
		return
	}
	window := 24 * time.Hour
	if wv := r.URL.Query().Get("window"); wv != "" {
		if d, err := time.ParseDuration(wv); err == nil && d > 0 {
			window = d
		}
	}
	status, err := h.deps.Vendors.VendorStatus(r.Context(), v.ID, window)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{"vendor": v, "status": status})
}

func (h *Handlers) vendorObservations(w http.ResponseWriter, r *http.Request) {
	rid := httpapi.RequestID(r.Context())
	v, err := h.deps.Vendors.VendorBySlug(r.Context(), r.PathValue("slug"))
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	if !v.PublicEnabled {
		httpapi.WriteError(w, h.log, rid, errors.NotFound("vendor_not_found", "vendor not found"))
		return
	}
	to := time.Now().UTC()
	from := to.Add(-24 * time.Hour)
	if fv := r.URL.Query().Get("from"); fv != "" {
		if t, err := time.Parse(time.RFC3339, fv); err == nil {
			from = t
		}
	}
	if tv := r.URL.Query().Get("to"); tv != "" {
		if t, err := time.Parse(time.RFC3339, tv); err == nil {
			to = t
		}
	}
	series, err := h.deps.Vendors.Series(r.Context(), v.ID, from, to, 3600)
	if err != nil {
		httpapi.WriteError(w, h.log, rid, err)
		return
	}
	httpapi.WriteData(w, rid, http.StatusOK, map[string]any{
		"vendor":   v,
		"from":     from.Format(time.RFC3339),
		"to":       to.Format(time.RFC3339),
		"series":   series,
	})
}
