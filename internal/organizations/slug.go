package organizations

import "regexp"

// slugRE matches organization/project slugs: 1-63 lowercase letters, digits,
// hyphens, not starting/ending with a hyphen.
var slugRE = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`)
