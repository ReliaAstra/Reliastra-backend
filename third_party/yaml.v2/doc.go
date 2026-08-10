// Package yamlv2 is a directory-replace shim for gopkg.in/yaml.v2.
//
// Rationale: some dependencies' go.mod files (prometheus/common, testify)
// require gopkg.in/yaml.v2 and gopkg.in/yaml.v3. Those hosts are unreachable
// from restricted build networks, and `replace ... => github.com/go-yaml/yaml
// v2.x` is rejected by the go command because the major-version suffix does
// not match the module path. Vendoring the stable, unchanged upstream source
// via directory replaces keeps the build hermetic everywhere.
//
// The source lives in ../yaml.v2 (module gopkg.in/yaml.v2) and is never
// modified.
package yamlv2
