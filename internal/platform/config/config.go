// Package config loads and validates Reliastra configuration from the
// environment. All values use the RELI_ prefix. Validation is strict:
// required values are missing => fail fast at startup; optional values have
// safe defaults. Never silently run with insecure production defaults.
package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config is the complete validated runtime configuration.
type Config struct {
	Env        string // development | test | production
	Service    string // api | scheduler | worker | notifier | migrate
	LogLevel   string
	HTTP       HTTPConfig
	Database   DatabaseConfig
	Redis      RedisConfig
	ObjectStore ObjectStoreConfig
	Auth       AuthConfig
	Scheduler  SchedulerConfig
	Worker     WorkerConfig
	Notifier   NotifierConfig
	Evidence   EvidenceConfig
	Incident   IncidentRulesConfig
	Encryption EncryptionConfig
	Plans      PlanConfig
	RateLimit  RateLimitConfig
	CORS       CORSConfig
	SMTP       SMTPConfig
	Slack      SlackConfig
	Public     PublicConfig
}

// HTTPConfig holds API server settings.
type HTTPConfig struct {
	Addr               string        // listen address, e.g. :8080
	ReadTimeout        time.Duration // server read timeout
	WriteTimeout       time.Duration // server write timeout
	IdleTimeout        time.Duration
	ShutdownTimeout    time.Duration
	MaxBodyBytes       int64 // request body limit
	MaxHeaderBytes     int
	TrustedProxyHeaders bool // trust X-Forwarded-For for client IP
	MetricsPath        string
	HealthLivePath     string
	HealthReadyPath    string
}

// DatabaseConfig holds PostgreSQL settings.
type DatabaseConfig struct {
	URL                    string
	MaxConns               int
	MinConns               int
	MaxConnLifetime        time.Duration
	MaxConnIdleTime        time.Duration
	ConnectTimeout         time.Duration
	StatementTimeout       time.Duration
	QueryTimeout           time.Duration // default per-query context timeout
	QueryMode              string        // "exec" (default) | "describe_exec" | "simple" | "cache"
}

// RedisConfig holds Redis settings. Redis is optional: when Addr is empty the
// platform degrades to in-memory coordination (single-process mode).
type RedisConfig struct {
	Addr         string
	Password     string
	DB           int
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	PoolSize     int
}

// ObjectStoreConfig selects the object storage backend.
type ObjectStoreConfig struct {
	Backend    string // s3 | filesystem
	Bucket     string
	Endpoint   string // e.g. s3.amazonaws.com or minio:9000
	Region     string
	AccessKey  string
	SecretKey  string
	UseSSL     bool
	FilesystemRoot string // used when Backend == filesystem
	Prefix     string // optional key prefix
	ForcePathStyle bool
}

// AuthConfig holds authentication/token settings.
type AuthConfig struct {
	SessionTTL       time.Duration
	SessionTokenBytes int
	APIKeyHashCost   int // argon2id parameters
	Argon2Memory     uint32
	Argon2Iterations uint32
	Argon2Parallelism uint8
	Argon2SaltLength uint32
	RegisterEnabled  bool
	MaxPasswordLength int
	MinPasswordLength int
}

// SchedulerConfig controls the durable scheduler.
type SchedulerConfig struct {
	PollInterval      time.Duration // how often the scheduler scans due monitors
	BatchSize         int           // monitors created per tick
	Lookahead         time.Duration // how far ahead jobs are created
	JitterMaxPct      float64       // max jitter as fraction of interval
	MissedJobWindow   time.Duration // jobs older than this are considered missed
	LeaseDuration     time.Duration // worker lease duration
	LeaseExpiryCheck  time.Duration // how often expired leases are reclaimed
	MaxRequeueAttempts int         // attempts before a job is abandoned
	MaxBackoff        time.Duration
	DetectionSweepInterval time.Duration
}

// WorkerConfig controls worker execution.
type WorkerConfig struct {
	Concurrency        int
	JobPollInterval    time.Duration
	JobPollBatch       int
	MaxResponseBytes   int64
	MaxRedirects       int
	ExecutionTimeout   time.Duration
	GracefulShutdown   time.Duration
	OrgFairnessMaxConcurrent int
	LeaseDuration      time.Duration
}

// NotifierConfig controls the outbox/notification worker.
type NotifierConfig struct {
	PollInterval   time.Duration
	BatchSize      int
	MaxDeliveryAttempts int
	BaseBackoff    time.Duration
	MaxBackoff     time.Duration
	DeadLetterAfter time.Duration
}

// EvidenceConfig controls evidence generation.
type EvidenceConfig struct {
	Enabled      bool
	StoragePrefix string
	PDFEnabled   bool
	MethodologyVersion string
	CorrelationVersion string
	ScoringConfigVersion string
	MaxObservationFetch int
}

// IncidentRulesConfig configures the deterministic incident detector.
type IncidentRulesConfig struct {
	ConsecutiveToCandidate int
	ConsecutiveToConfirm   int
	FailureRateWindow      int
	FailureRateToCandidate float64
	FailureRateToConfirm   float64
	RegionsToConfirm       int
	HealthyToResolve       int
	Lookback               time.Duration
	MaxObservations        int
}

// EncryptionConfig configures envelope encryption for secrets at rest.
type EncryptionConfig struct {
	// MasterKey is hex-encoded 32-byte AES-256 key (dev) OR the file path /
	// env name from which it is loaded in production. See docs/security.
	MasterKey string
	KeyVersion int
}

// PlanConfig defines plan-based limits (entitlements).
type PlanConfig struct {
	DefaultPlan string
	Plans       map[string]PlanLimits
}

// PlanLimits is a single plan's entitlement set. Config-driven, never
// hardcoded in business logic.
type PlanLimits struct {
	MaxMonitors          int
	MinIntervalSeconds   int
	MaxProjects          int
	MaxMembers           int
	MaxEvidencePerDay    int
	APIRequestsPerMinute int
	CheckRetentionDays   int
	MaxDependencies      int
	MaxServices          int
	MaxRegions           int
	MaxAPIKeys           int
}

// RateLimitConfig defines per-scope limits.
type RateLimitConfig struct {
	Enabled        bool
	RedisEnabled   bool
	PerIPPerMinute int
	PerUserPerMinute int
	PerOrgPerMinute int
	PerAPIKeyPerMinute int
	AuthPerIPPerMinute int
	PublicPerMinute int
	EvidencePerOrgPerHour int
}

// CORSConfig controls cross-origin behavior.
type CORSConfig struct {
	AllowedOrigins []string
	AllowedHeaders []string
	MaxAgeSeconds  int
}

// SMTPConfig configures outbound email.
type SMTPConfig struct {
	Host     string
	Port     int
	Username string
	Password string
	From     string
	Enabled  bool
	Timeout  time.Duration
}

// SlackConfig configures Slack webhook notifications.
type SlackConfig struct {
	Enabled bool
	Timeout time.Duration
}

// PublicConfig controls public vendor tracking.
type PublicConfig struct {
	Enabled        bool
	TrackingDomain string
	ObservationRetention time.Duration
}

// Load reads configuration from the environment and validates it.
func Load() (*Config, error) {
	c := &Config{
		Env:        get("RELI_ENV", "development"),
		Service:    get("RELI_SERVICE", "api"),
		LogLevel:   get("RELI_LOG_LEVEL", "info"),
		HTTP: HTTPConfig{
			Addr:            get("RELI_HTTP_ADDR", ":8080"),
			ReadTimeout:     dur("RELI_HTTP_READ_TIMEOUT", 15*time.Second),
			WriteTimeout:    dur("RELI_HTTP_WRITE_TIMEOUT", 30*time.Second),
			IdleTimeout:     dur("RELI_HTTP_IDLE_TIMEOUT", 60*time.Second),
			ShutdownTimeout: dur("RELI_HTTP_SHUTDOWN_TIMEOUT", 20*time.Second),
			MaxBodyBytes:    int64(getInt("RELI_HTTP_MAX_BODY_BYTES", 1<<20)),
			MaxHeaderBytes:  getInt("RELI_HTTP_MAX_HEADER_BYTES", 1<<20),
			TrustedProxyHeaders: getBool("RELI_HTTP_TRUST_PROXY_HEADERS", false),
			MetricsPath:     get("RELI_METRICS_PATH", "/metrics"),
			HealthLivePath:  get("RELI_HEALTH_LIVE_PATH", "/health/live"),
			HealthReadyPath: get("RELI_HEALTH_READY_PATH", "/health/ready"),
		},
		Database: DatabaseConfig{
			URL:             get("RELI_DATABASE_URL", ""),
			MaxConns:        getInt("RELI_DATABASE_MAX_CONNS", 20),
			MinConns:        getInt("RELI_DATABASE_MIN_CONNS", 2),
			MaxConnLifetime: dur("RELI_DATABASE_MAX_CONN_LIFETIME", time.Hour),
			MaxConnIdleTime: dur("RELI_DATABASE_MAX_IDLE_TIME", 30*time.Minute),
			ConnectTimeout:  dur("RELI_DATABASE_CONNECT_TIMEOUT", 10*time.Second),
			StatementTimeout: dur("RELI_DATABASE_STATEMENT_TIMEOUT", 30*time.Second),
			QueryTimeout:    dur("RELI_DATABASE_QUERY_TIMEOUT", 10*time.Second),
			// "describe_exec" (default) describes parameters before binding,
			// so jsonb/timestamptz parameters are typed correctly with no
			// statement cache — compatible with PGlite, RDS proxies and
			// PgBouncer transaction mode. "exec" skips describe;
			// "simple" uses the simple protocol; "cache" restores the pgx
			// default prepared-statement cache where parse overhead matters.
			QueryMode: get("RELI_DATABASE_QUERY_MODE", "exec"),
		},
		Redis: RedisConfig{
			Addr:         get("RELI_REDIS_ADDR", ""),
			Password:     get("RELI_REDIS_PASSWORD", ""),
			DB:           getInt("RELI_REDIS_DB", 0),
			DialTimeout:  dur("RELI_REDIS_DIAL_TIMEOUT", 5*time.Second),
			ReadTimeout:  dur("RELI_REDIS_READ_TIMEOUT", 3*time.Second),
			WriteTimeout: dur("RELI_REDIS_WRITE_TIMEOUT", 3*time.Second),
			PoolSize:     getInt("RELI_REDIS_POOL_SIZE", 16),
		},
		ObjectStore: ObjectStoreConfig{
			Backend:    get("RELI_OBJECT_STORE_BACKEND", "filesystem"),
			Bucket:     get("RELI_OBJECT_STORE_BUCKET", "reliastra-evidence"),
			Endpoint:   get("RELI_OBJECT_STORE_ENDPOINT", ""),
			Region:     get("RELI_OBJECT_STORE_REGION", "us-east-1"),
			AccessKey:  get("RELI_OBJECT_STORE_ACCESS_KEY", ""),
			SecretKey:  get("RELI_OBJECT_STORE_SECRET_KEY", ""),
			UseSSL:     getBool("RELI_OBJECT_STORE_USE_SSL", false),
			FilesystemRoot: get("RELI_OBJECT_STORE_FS_ROOT", "./data/objectstore"),
			Prefix:     get("RELI_OBJECT_STORE_PREFIX", ""),
			ForcePathStyle: getBool("RELI_OBJECT_STORE_FORCE_PATH_STYLE", true),
		},
		Auth: AuthConfig{
			SessionTTL:        dur("RELI_AUTH_SESSION_TTL", 7*24*time.Hour),
			SessionTokenBytes: getInt("RELI_AUTH_SESSION_TOKEN_BYTES", 32),
			RegisterEnabled:   getBool("RELI_AUTH_REGISTER_ENABLED", true),
			Argon2Memory:      uint32(getInt("RELI_AUTH_ARGON2_MEMORY", 64*1024)),
			Argon2Iterations:  uint32(getInt("RELI_AUTH_ARGON2_ITERATIONS", 3)),
			Argon2Parallelism: uint8(getInt("RELI_AUTH_ARGON2_PARALLELISM", 2)),
			Argon2SaltLength:  uint32(getInt("RELI_AUTH_ARGON2_SALT_LENGTH", 16)),
			MinPasswordLength: getInt("RELI_AUTH_MIN_PASSWORD_LENGTH", 10),
			MaxPasswordLength: getInt("RELI_AUTH_MAX_PASSWORD_LENGTH", 128),
		},
		Scheduler: SchedulerConfig{
			PollInterval:      dur("RELI_SCHEDULER_POLL_INTERVAL", 5*time.Second),
			BatchSize:         getInt("RELI_SCHEDULER_BATCH_SIZE", 500),
			Lookahead:         dur("RELI_SCHEDULER_LOOKAHEAD", 5*time.Minute),
			JitterMaxPct:      getFloat("RELI_SCHEDULER_JITTER_MAX_PCT", 0.10),
			MissedJobWindow:   dur("RELI_SCHEDULER_MISSED_JOB_WINDOW", 10*time.Minute),
			LeaseDuration:     dur("RELI_WORKER_LEASE_DURATION", 2*time.Minute),
			LeaseExpiryCheck:  dur("RELI_SCHEDULER_LEASE_EXPIRY_CHECK", 30*time.Second),
			MaxRequeueAttempts: getInt("RELI_SCHEDULER_MAX_REQUEUE_ATTEMPTS", 5),
			MaxBackoff:        dur("RELI_SCHEDULER_MAX_BACKOFF", 30*time.Minute),
			DetectionSweepInterval: dur("RELI_SCHEDULER_DETECTION_SWEEP_INTERVAL", 1*time.Minute),
		},
		Worker: WorkerConfig{
			Concurrency:      getInt("RELI_WORKER_CONCURRENCY", 8),
			JobPollInterval:  dur("RELI_WORKER_POLL_INTERVAL", 1*time.Second),
			JobPollBatch:     getInt("RELI_WORKER_POLL_BATCH", 10),
			MaxResponseBytes: int64(getInt("RELI_WORKER_MAX_RESPONSE_BYTES", 1<<20)),
			MaxRedirects:     getInt("RELI_WORKER_MAX_REDIRECTS", 5),
			ExecutionTimeout: dur("RELI_WORKER_EXECUTION_TIMEOUT", 30*time.Second),
			GracefulShutdown: dur("RELI_WORKER_GRACEFUL_SHUTDOWN", 20*time.Second),
			OrgFairnessMaxConcurrent: getInt("RELI_WORKER_ORG_FAIRNESS_MAX", 4),
			LeaseDuration:    dur("RELI_WORKER_LEASE_DURATION", 2*time.Minute),
		},
		Notifier: NotifierConfig{
			PollInterval:   dur("RELI_NOTIFIER_POLL_INTERVAL", 2*time.Second),
			BatchSize:      getInt("RELI_NOTIFIER_BATCH_SIZE", 100),
			MaxDeliveryAttempts: getInt("RELI_NOTIFIER_MAX_DELIVERY_ATTEMPTS", 6),
			BaseBackoff:    dur("RELI_NOTIFIER_BASE_BACKOFF", 30*time.Second),
			MaxBackoff:     dur("RELI_NOTIFIER_MAX_BACKOFF", 1*time.Hour),
			DeadLetterAfter: dur("RELI_NOTIFIER_DEAD_LETTER_AFTER", 24*time.Hour),
		},
		Evidence: EvidenceConfig{
			Enabled:        getBool("RELI_EVIDENCE_ENABLED", true),
			StoragePrefix:  get("RELI_EVIDENCE_STORAGE_PREFIX", "evidence"),
			PDFEnabled:     getBool("RELI_EVIDENCE_PDF_ENABLED", true),
			MethodologyVersion: get("RELI_EVIDENCE_METHODOLOGY_VERSION", "v1"),
			CorrelationVersion: get("RELI_EVIDENCE_CORRELATION_VERSION", "v1"),
			ScoringConfigVersion: get("RELI_EVIDENCE_SCORING_CONFIG_VERSION", "v1"),
			MaxObservationFetch: getInt("RELI_EVIDENCE_MAX_OBSERVATION_FETCH", 5000),
		},
		Incident: IncidentRulesConfig{
			ConsecutiveToCandidate: getInt("RELI_INCIDENT_CONSECUTIVE_CANDIDATE", 3),
			ConsecutiveToConfirm:   getInt("RELI_INCIDENT_CONSECUTIVE_CONFIRM", 5),
			FailureRateWindow:      getInt("RELI_INCIDENT_FAILURE_RATE_WINDOW", 10),
			FailureRateToCandidate: getFloat("RELI_INCIDENT_FAILURE_RATE_CANDIDATE", 0.6),
			FailureRateToConfirm:   getFloat("RELI_INCIDENT_FAILURE_RATE_CONFIRM", 0.8),
			RegionsToConfirm:       getInt("RELI_INCIDENT_REGIONS_TO_CONFIRM", 2),
			HealthyToResolve:       getInt("RELI_INCIDENT_HEALTHY_TO_RESOLVE", 3),
			Lookback:               dur("RELI_INCIDENT_LOOKBACK", 30*time.Minute),
			MaxObservations:        getInt("RELI_INCIDENT_MAX_OBSERVATIONS", 100),
		},
		Encryption: EncryptionConfig{
			MasterKey: get("RELI_ENCRYPTION_MASTER_KEY", ""),
			KeyVersion: getInt("RELI_ENCRYPTION_KEY_VERSION", 1),
		},
		Plans: PlanConfig{
			DefaultPlan: get("RELI_PLANS_DEFAULT", "free"),
			Plans: map[string]PlanLimits{
				"free": {
					MaxMonitors: 1, MinIntervalSeconds: 300,
					MaxProjects: 1, MaxMembers: 1, MaxEvidencePerDay: 1,
					APIRequestsPerMinute: 60, CheckRetentionDays: 7,
					MaxDependencies: 10, MaxServices: 3, MaxRegions: 1,
					MaxAPIKeys: 1,
				},
				"standard": {
					MaxMonitors: 25, MinIntervalSeconds: 60,
					MaxProjects: 3, MaxMembers: 10, MaxEvidencePerDay: 10,
					APIRequestsPerMinute: 600, CheckRetentionDays: 30,
					MaxDependencies: 100, MaxServices: 50, MaxRegions: 3,
					MaxAPIKeys: 10,
				},
				"professional": {
					MaxMonitors: 100, MinIntervalSeconds: 30,
					MaxProjects: 10, MaxMembers: 50, MaxEvidencePerDay: 100,
					APIRequestsPerMinute: 3000, CheckRetentionDays: 180,
					MaxDependencies: 500, MaxServices: 200, MaxRegions: 10,
					MaxAPIKeys: 50,
				},
			},
		},
		RateLimit: RateLimitConfig{
			Enabled:            getBool("RELI_RATE_LIMIT_ENABLED", true),
			RedisEnabled:       getBool("RELI_RATE_LIMIT_REDIS_ENABLED", true),
			PerIPPerMinute:     getInt("RELI_RATE_LIMIT_PER_IP_PER_MINUTE", 300),
			PerUserPerMinute:   getInt("RELI_RATE_LIMIT_PER_USER_PER_MINUTE", 600),
			PerOrgPerMinute:    getInt("RELI_RATE_LIMIT_PER_ORG_PER_MINUTE", 2000),
			PerAPIKeyPerMinute: getInt("RELI_RATE_LIMIT_PER_API_KEY_PER_MINUTE", 1200),
			AuthPerIPPerMinute: getInt("RELI_RATE_LIMIT_AUTH_PER_IP_PER_MINUTE", 20),
			PublicPerMinute:    getInt("RELI_RATE_LIMIT_PUBLIC_PER_MINUTE", 120),
			EvidencePerOrgPerHour: getInt("RELI_RATE_LIMIT_EVIDENCE_PER_ORG_PER_HOUR", 20),
		},
		CORS: CORSConfig{
			AllowedOrigins: split(get("RELI_CORS_ALLOWED_ORIGINS", "")),
			AllowedHeaders: []string{"Content-Type", "Authorization", "X-Request-Id", "Idempotency-Key"},
			MaxAgeSeconds:  getInt("RELI_CORS_MAX_AGE", 600),
		},
		SMTP: SMTPConfig{
			Host: get("RELI_SMTP_HOST", ""), Port: getInt("RELI_SMTP_PORT", 587),
			Username: get("RELI_SMTP_USERNAME", ""), Password: get("RELI_SMTP_PASSWORD", ""),
			From: get("RELI_SMTP_FROM", "Reliastra <no-reply@reliastra.dev>"),
			Enabled: getBool("RELI_SMTP_ENABLED", false), Timeout: dur("RELI_SMTP_TIMEOUT", 10*time.Second),
		},
		Slack: SlackConfig{
			Enabled: getBool("RELI_SLACK_ENABLED", false), Timeout: dur("RELI_SLACK_TIMEOUT", 10*time.Second),
		},
		Public: PublicConfig{
			Enabled: getBool("RELI_PUBLIC_TRACKING_ENABLED", true),
			TrackingDomain: get("RELI_PUBLIC_TRACKING_DOMAIN", "track.reliastra.dev"),
			ObservationRetention: dur("RELI_PUBLIC_OBSERVATION_RETENTION", 90*24*time.Hour),
		},
	}

	if err := c.validate(); err != nil {
		return nil, err
	}
	return c, nil
}

func (c *Config) validate() error {
	switch c.Env {
	case "development", "test", "production":
	default:
		return fmt.Errorf("config: RELI_ENV must be development, test or production (got %q)", c.Env)
	}
	if c.Database.URL == "" {
		return fmt.Errorf("config: RELI_DATABASE_URL is required")
	}
	if c.Database.MaxConns < 1 || c.Database.MinConns < 0 {
		return fmt.Errorf("config: invalid database pool limits")
	}
	if c.Env == "production" {
		if c.Encryption.MasterKey == "" {
			return fmt.Errorf("config: RELI_ENCRYPTION_MASTER_KEY is required in production")
		}
		if c.SMTP.Enabled && c.SMTP.Host == "" {
			return fmt.Errorf("config: RELI_SMTP_HOST required when email enabled")
		}
	}
	switch c.ObjectStore.Backend {
	case "s3", "filesystem":
	default:
		return fmt.Errorf("config: RELI_OBJECT_STORE_BACKEND must be s3 or filesystem")
	}
	if c.ObjectStore.Backend == "s3" {
		if c.ObjectStore.Endpoint == "" || c.ObjectStore.Bucket == "" {
			return fmt.Errorf("config: object store backend s3 requires RELI_OBJECT_STORE_ENDPOINT and RELI_OBJECT_STORE_BUCKET")
		}
	}
	if c.Worker.Concurrency < 1 {
		return fmt.Errorf("config: RELI_WORKER_CONCURRENCY must be >= 1")
	}
	if c.Scheduler.JitterMaxPct < 0 || c.Scheduler.JitterMaxPct > 0.5 {
		return fmt.Errorf("config: RELI_SCHEDULER_JITTER_MAX_PCT must be in [0, 0.5]")
	}
	if c.Plans.DefaultPlan != "" {
		if _, ok := c.Plans.Plans[c.Plans.DefaultPlan]; !ok {
			return fmt.Errorf("config: default plan %q not defined", c.Plans.DefaultPlan)
		}
	}
	return nil
}

func get(k, def string) string {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		return v
	}
	return def
}

func getInt(k string, def int) int {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func getBool(k string, def bool) bool {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
	}
	return def
}

func getFloat(k string, def float64) float64 {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

func dur(k string, def time.Duration) time.Duration {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}

func split(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

// ValidateURL parses and returns a URL, used by components that take URLs in
// config (e.g. object store endpoints).
func ValidateURL(s string) (*url.URL, error) {
	u, err := url.Parse(s)
	if err != nil {
		return nil, fmt.Errorf("config: invalid URL %q: %w", s, err)
	}
	return u, nil
}
