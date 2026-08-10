// Command migrate applies database migrations deterministically.
//
// Usage:
//
//	migrate up            apply all pending migrations
//	migrate down          roll back the most recent migration
//	migrate status        print migration state
//	migrate seed          apply seed data (development only)
package main

import (
	"context"
	"fmt"
	"os"


	"github.com/ReliaAstra/reliastra-backend/internal/platform/app"
	"github.com/ReliaAstra/reliastra-backend/internal/platform/database"
	"github.com/ReliaAstra/reliastra-backend/internal/seed"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: migrate <up|down|status|seed>")
		os.Exit(2)
	}
	cfg, err := app.LoadConfig("migrate")
	if err != nil {
		fmt.Fprintln(os.Stderr, "config error:", err)
		os.Exit(1)
	}
	ctx := context.Background()
	pool, err := database.Connect(ctx, cfg.Database)
	if err != nil {
		fmt.Fprintln(os.Stderr, "database connect error:", err)
		os.Exit(1)
	}
	defer pool.Close()

	m := database.NewMigrator(pool.Pool)
	switch os.Args[1] {
	case "up":
		applied, err := m.Up(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, "migration failed:", err)
			os.Exit(1)
		}
		if len(applied) == 0 {
			fmt.Println("no pending migrations")
		} else {
			fmt.Printf("applied %d migration(s): %v\n", len(applied), applied)
		}
	case "down":
		if err := m.Down(ctx); err != nil {
			fmt.Fprintln(os.Stderr, "rollback failed:", err)
			os.Exit(1)
		}
		fmt.Println("rolled back one migration")
	case "status":
		rows, err := m.Status(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, "status failed:", err)
			os.Exit(1)
		}
		for _, r := range rows {
			state := "pending"
			if r.Applied {
				state = "applied"
			}
			fmt.Printf("%04d %-40s %s\n", r.Version, r.Name, state)
		}
	case "seed":
		if err := seed.Run(ctx, pool.Pool, cfg); err != nil {
			fmt.Fprintln(os.Stderr, "seed failed:", err)
			os.Exit(1)
		}
		fmt.Println("seed data applied")
	default:
		fmt.Fprintln(os.Stderr, "unknown command:", os.Args[1])
		os.Exit(2)
	}
}
