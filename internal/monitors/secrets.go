package monitors

import (
	"encoding/json"
	"strings"
)

// SplitSecrets removes sensitive values from the HTTP config and returns them
// separately for encrypted storage. Sensitive headers are those listed in
// SensitiveHeaders plus the well-known credential headers. The config retains
// a redacted placeholder ("<redacted>") so the shape stays self-describing.
func SplitSecrets(cfg *HTTPConfig) (map[string]string, string) {
	secrets := map[string]string{}
	sensitive := map[string]bool{
		"authorization":        true,
		"cookie":               true,
		"proxy-authorization":  true,
	}
	for _, h := range cfg.SensitiveHeaders {
		sensitive[strings.ToLower(h)] = true
	}
	for k, v := range cfg.Headers {
		if v != "" && sensitive[strings.ToLower(k)] {
			secrets[k] = v
			cfg.Headers[k] = "<redacted>"
		}
	}
	secretBody := ""
	if cfg.BodySensitive && cfg.Body != "" {
		secretBody = cfg.Body
		cfg.Body = "<redacted>"
	}
	return secrets, secretBody
}

// ExtractSecrets parses a raw configuration, extracts sensitive values, and
// returns the redacted configuration (safe to persist), the secrets map and
// the secret body. The raw input is not modified.
func ExtractSecrets(raw json.RawMessage) (redacted json.RawMessage, secrets map[string]string, secretBody string, err error) {
	cfg, err := parseHTTPConfig(raw)
	if err != nil {
		return nil, nil, "", err
	}
	secrets, secretBody = SplitSecrets(cfg)
	redacted, err = json.Marshal(cfg)
	if err != nil {
		return nil, nil, "", err
	}
	return redacted, secrets, secretBody, nil
}
