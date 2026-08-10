// Package metrics centralizes the Prometheus metric registry and the metric
// definitions the whole platform records against. Components should call the
// helpers here rather than creating ad-hoc prometheus metrics, so names stay
// stable and documented.
package metrics

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Namespace is common to all Reliastra metrics.
const Namespace = "reliastra"

// Registry is the process-wide registry (per-process, not global state shared
// across processes; each binary gets its own).
var Registry = prometheus.NewRegistry()

var (
	// API
	APIRequestsTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "api_requests_total",
		Help: "Total HTTP requests handled by the API.",
	}, []string{"method", "path", "status"})
	APIRequestDuration = promauto.With(Registry).NewHistogramVec(prometheus.HistogramOpts{
		Namespace: Namespace, Name: "api_request_duration_seconds",
		Help:    "HTTP request latency.",
		Buckets: prometheus.DefBuckets,
	}, []string{"method", "path"})

	// Jobs
	JobsCreatedTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_created_total",
		Help: "Check jobs created by the scheduler.",
	}, []string{"monitor_type"})
	JobsCompletedTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_completed_total",
		Help: "Check jobs completed by workers.",
	}, []string{"status"})
	JobsFailedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_failed_total",
		Help: "Check jobs that failed after exhausting retries.",
	})
	JobsRetriedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_retried_total",
		Help: "Check jobs retried (attempt > 1).",
	})
	JobsExpiredTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_expired_total",
		Help: "Leases that expired and were re-queued.",
	})
	JobsRequeuedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "jobs_requeued_total",
		Help: "Jobs re-queued after worker death/lease expiry.",
	})
	JobLeaseWaitSeconds = promauto.With(Registry).NewHistogram(prometheus.HistogramOpts{
		Namespace: Namespace, Name: "job_lease_wait_seconds",
		Help:    "Time between scheduled_for and lease acquisition.",
		Buckets: prometheus.DefBuckets,
	})

	// Workers
	WorkerActiveJobs = promauto.With(Registry).NewGauge(prometheus.GaugeOpts{
		Namespace: Namespace, Name: "worker_active_jobs",
		Help: "Number of jobs currently being executed by this worker process.",
	})
	WorkerCapacity = promauto.With(Registry).NewGauge(prometheus.GaugeOpts{
		Namespace: Namespace, Name: "worker_capacity",
		Help: "Maximum concurrent jobs this worker process will run.",
	})

	// Checks
	CheckSuccessTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "check_success_total",
		Help: "Checks that succeeded.",
	}, []string{"monitor_type", "region"})
	CheckFailureTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "check_failure_total",
		Help: "Checks that failed.",
	}, []string{"monitor_type", "region", "failure_class"})

	// Incidents
	IncidentCreatedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "incident_created_total",
		Help: "Incident candidates created.",
	})
	IncidentConfirmedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "incident_confirmed_total",
		Help: "Incidents confirmed.",
	})
	IncidentResolvedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "incident_resolved_total",
		Help: "Incidents resolved.",
	})
	IncidentFalsePositiveTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "incident_false_positive_total",
		Help: "Incidents marked false positive.",
	})

	// Correlation
	CorrelationRunsTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "correlation_runs_total",
		Help: "Correlation runs executed.",
	})

	// Evidence
	EvidenceGeneratedTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "evidence_generated_total",
		Help: "Evidence artifacts generated.",
	})
	EvidenceGenerationFailuresTotal = promauto.With(Registry).NewCounter(prometheus.CounterOpts{
		Namespace: Namespace, Name: "evidence_generation_failures_total",
		Help: "Evidence generation failures.",
	})

	// Notifications
	NotificationSentTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "notification_sent_total",
		Help: "Notifications delivered.",
	}, []string{"channel_type"})
	NotificationFailedTotal = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "notification_failed_total",
		Help: "Notifications that failed.",
	}, []string{"channel_type"})

	// Database
	DBPoolConnections = promauto.With(Registry).NewGauge(prometheus.GaugeOpts{
		Namespace: Namespace, Name: "database_pool_connections",
		Help: "Current number of database connections in the pool.",
	})
	DBQueryDuration = promauto.With(Registry).NewHistogramVec(prometheus.HistogramOpts{
		Namespace: Namespace, Name: "database_query_duration_seconds",
		Help:    "Database query latency.",
		Buckets: prometheus.DefBuckets,
	}, []string{"op"})

	// Redis
	RedisOperations = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "redis_operations_total",
		Help: "Redis operations by result.",
	}, []string{"result"})

	// Outbox
	OutboxEventsProcessed = promauto.With(Registry).NewCounterVec(prometheus.CounterOpts{
		Namespace: Namespace, Name: "outbox_events_processed_total",
		Help: "Outbox events processed.",
	}, []string{"event_type", "result"})
)

// ObserveDuration records fn() execution time into the given histogram vec.
func ObserveDuration(vec *prometheus.HistogramVec, labels ...string) func() {
	start := time.Now()
	return func() { vec.WithLabelValues(labels...).Observe(time.Since(start).Seconds()) }
}
