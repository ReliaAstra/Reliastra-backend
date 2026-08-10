package httpapi

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// WriteMetrics serves Prometheus metrics from a registry.
func WriteMetrics(w http.ResponseWriter, r *http.Request, registry *prometheus.Registry) {
	h := promhttp.HandlerFor(registry, promhttp.HandlerOpts{})
	h.ServeHTTP(w, r)
}
