// Package migrations embeds the SQL migration files and provides a
// deterministic, transactional migration runner.
//
// Migration files are named NNNN_name.up.sql / NNNN_name.down.sql. The runner
// applies each pending migration inside a single transaction and records it in
// schema_migrations. Down migrations are provided where practical and applied
// one version at a time by `migrate down`.
package migrations

import (
	"embed"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

//go:embed *.sql
var FS embed.FS

// Migration is a single versioned migration.
type Migration struct {
	Version int
	Name    string
	Up      string
	Down    string
}

// All returns migrations sorted by version.
func All() ([]Migration, error) {
	entries, err := FS.ReadDir(".")
	if err != nil {
		return nil, fmt.Errorf("migrations: read dir: %w", err)
	}
	type part struct {
		version int
		name    string
		dir     string // up | down
		body    string
	}
	var parts []part
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		fn := e.Name()
		// Filename format: NNNN_name.up.sql / NNNN_name.down.sql
		dot := strings.LastIndex(fn, ".")
		if dot < 0 {
			continue
		}
		base := fn[:dot] // e.g. "0001_tenancy.up"
		idx := strings.LastIndex(base, ".")
		if idx < 0 {
			continue
		}
		verAndName, dir := base[:idx], base[idx+1:] // "0001_tenancy", "up"
		if dir != "up" && dir != "down" {
			continue
		}
		sep := strings.Index(verAndName, "_")
		if sep < 0 {
			return nil, fmt.Errorf("migrations: invalid filename %q (want NNNN_name.up.sql)", fn)
		}
		ver, err := strconv.Atoi(verAndName[:sep])
		if err != nil {
			return nil, fmt.Errorf("migrations: invalid version in %q", fn)
		}
		body, err := FS.ReadFile(fn)
		if err != nil {
			return nil, err
		}
		parts = append(parts, part{version: ver, name: verAndName[sep+1:], dir: dir, body: string(body)})
	}
	sort.Slice(parts, func(i, j int) bool {
		if parts[i].version != parts[j].version {
			return parts[i].version < parts[j].version
		}
		return parts[i].dir == "up" // up before down within a version
	})

	// One Migration per version: the up part provides Up; the down part
	// provides Down. A version with only a down file is invalid.
	var out []Migration
	for i := 0; i < len(parts); i++ {
		p := parts[i]
		if p.dir != "up" {
			continue
		}
		m := Migration{Version: p.version, Name: p.name, Up: p.body}
		for j := 0; j < len(parts); j++ {
			if parts[j].version == p.version && parts[j].dir == "down" {
				m.Down = parts[j].body
			}
		}
		out = append(out, m)
	}
	return out, nil
}
