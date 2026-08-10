// Package redis provides a small wrapper around go-redis. Redis is strictly
// auxiliary (coordination, caching, rate limiting); PostgreSQL remains the
// source of truth. When the configured address is empty, components degrade
// to local in-memory behavior and the platform stays correct on one node.
package redis

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/ReliaAstra/reliastra-backend/internal/platform/config"
)

// Client wraps go-redis.
type Client struct {
	*redis.Client
	Addr string
}

// Connect opens a Redis client and pings it. Returns (nil, nil) when the
// address is empty (Redis disabled).
func Connect(ctx context.Context, cfg config.RedisConfig) (*Client, error) {
	if cfg.Addr == "" {
		return nil, nil
	}
	rdb := redis.NewClient(&redis.Options{
		Addr:         cfg.Addr,
		Password:     cfg.Password,
		DB:           cfg.DB,
		DialTimeout:  cfg.DialTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		PoolSize:     cfg.PoolSize,
	})
	pingCtx, cancel := context.WithTimeout(ctx, cfg.DialTimeout)
	defer cancel()
	if err := rdb.Ping(pingCtx).Err(); err != nil {
		rdb.Close()
		return nil, fmt.Errorf("redis: ping %s: %w", cfg.Addr, err)
	}
	return &Client{Client: rdb, Addr: cfg.Addr}, nil
}

// Available reports whether Redis is connected.
func (c *Client) Available() bool { return c != nil && c.Client != nil }

// Close closes the client when present.
func (c *Client) Close() error {
	if !c.Available() {
		return nil
	}
	return c.Client.Close()
}

// Instrumented limits to keep imports honest.
var _ = time.Second
