module github.com/ReliaAstra/reliastra-backend

go 1.25

require (
	github.com/go-pdf/fpdf v0.9.0
	github.com/jackc/pgx/v5 v5.7.1
	github.com/minio/minio-go/v7 v7.0.81
	github.com/prometheus/client_golang v1.20.5
	github.com/redis/go-redis/v9 v9.7.0
	golang.org/x/crypto v0.31.0
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/go-ini/ini v1.67.0 // indirect
	github.com/goccy/go-json v0.10.3 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/klauspost/compress v1.17.11 // indirect
	github.com/klauspost/cpuid/v2 v2.2.8 // indirect
	github.com/minio/md5-simd v1.1.2 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.1 // indirect
	github.com/prometheus/common v0.55.0 // indirect
	github.com/prometheus/procfs v0.15.1 // indirect
	github.com/rs/xid v1.6.0 // indirect
	golang.org/x/net v0.30.0 // indirect
	golang.org/x/sync v0.10.0 // indirect
	golang.org/x/sys v0.28.0 // indirect
	golang.org/x/text v0.21.0 // indirect
	google.golang.org/protobuf v1.34.2 // indirect
)

// Restricted networks cannot reach go.googlesource.com, google.golang.org,
// gopkg.in or go.yaml.in. These replace directives map canonical module paths
// to official GitHub mirrors (identical code and tags) or to vendored
// directories (yaml, whose major-version module paths cannot be replaced by
// GitHub tags). They are harmless on any network and keep the build hermetic.
replace (
	golang.org/x/crypto => github.com/golang/crypto v0.31.0
	golang.org/x/image => github.com/golang/image v0.23.0
	golang.org/x/net => github.com/golang/net v0.33.0
	golang.org/x/sync => github.com/golang/sync v0.10.0
	golang.org/x/sys => github.com/golang/sys v0.28.0
	golang.org/x/term => github.com/golang/term v0.27.0
	golang.org/x/text => github.com/golang/text v0.21.0
	google.golang.org/protobuf => github.com/protocolbuffers/protobuf-go v1.36.1
	gopkg.in/check.v1 => ./third_party/check.v1
	gopkg.in/yaml.v2 => ./third_party/yaml.v2
	gopkg.in/yaml.v3 => ./third_party/yaml.v3
)
