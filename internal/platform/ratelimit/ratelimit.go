// Package ratelimit implements distributed (Redis) and local (in-memory)
// fixed-window rate limiting with a common interface.
package ratelimit

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

		"github.com/ReliaAstra/reliastra-backend/pkg/metrics"
)

// Result of an Allow call.
type Result struct {
	Allowed    bool
	RetryAfter time.Duration
	Limit      int
	Remaining  int
}

// Limiter is the rate limiter interface.
type Limiter interface {
	// Allow increments the counter for key and reports whether the request
	// may proceed. window must be > 0.
	Allow(ctx context.Context, key string, limit int, window time.Duration) (Result, error)
}

// FixedWindow implements Limiter with a fixed time window.
type FixedWindow struct {
	rc *redis.Client // nil => in-memory
	mu sync.Mutex
	// in-memory state: key -> (windowStartUnix, count)
	mem map[string]memEntry
}

type memEntry struct {
	start int64
	count int64
}

// New creates a limiter. rc may be nil to use the in-memory backend.
func New(rc *redis.Client) *FixedWindow {
	return &FixedWindow{rc: rc, mem: make(map[string]memEntry)}
}

const allowScript = `
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then ttl = ARGV[1] end
if c > tonumber(ARGV[2]) then
  return {0, ttl, tonumber(ARGV[2]), 0}
end
return {1, ttl, tonumber(ARGV[2]), tonumber(ARGV[2]) - c}
`

// Allow implements Limiter.
func (f *FixedWindow) Allow(ctx context.Context, key string, limit int, window time.Duration) (Result, error) {
	if limit <= 0 {
		return Result{Allowed: false, RetryAfter: window, Limit: limit}, nil
	}
	if f.rc != nil {
		res, err := f.allowRedis(ctx, key, limit, window)
		if err == nil {
			metrics.RedisOperations.WithLabelValues("ok").Inc()
		} else {
			metrics.RedisOperations.WithLabelValues("error").Inc()
		}
		return res, err
	}
	return f.allowMem(key, limit, window), nil
}

func (f *FixedWindow) allowRedis(ctx context.Context, key string, limit int, window time.Duration) (Result, error) {
	secs := int64(window / time.Second)
	if secs < 1 {
		secs = 1
	}
	res, err := f.rc.Eval(ctx, allowScript, []string{key}, secs, limit).Slice()
	if err != nil {
		return Result{}, fmt.Errorf("ratelimit: redis eval: %w", err)
	}
	allowed := res[0].(int64) == 1
	retry := time.Duration(res[1].(int64)) * time.Second
	lim := int(res[2].(int64))
	remaining := int(res[3].(int64))
	return Result{Allowed: allowed, RetryAfter: retry, Limit: lim, Remaining: remaining}, nil
}

func (f *FixedWindow) allowMem(key string, limit int, window time.Duration) Result {
	now := time.Now().UTC().Unix()
	f.mu.Lock()
	defer f.mu.Unlock()
	e, ok := f.mem[key]
	if !ok || now-e.start >= int64(window/time.Second) {
		e = memEntry{start: now, count: 0}
	}
	e.count++
	f.mem[key] = e
	remaining := limit - int(e.count)
	if remaining < 0 {
		remaining = 0
	}
	return Result{
		Allowed:    int(e.count) <= limit,
		RetryAfter: time.Duration(e.start+int64(window/time.Second)-now) * time.Second,
		Limit:      limit,
		Remaining:  remaining,
	}
}

// Close stops background goroutines if any (none in Phase 1).
func (f *FixedWindow) Close() {}

