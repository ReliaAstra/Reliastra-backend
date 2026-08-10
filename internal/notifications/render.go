package notifications

import (
	"fmt"
	"strings"
)

// Render builds a human message for an event type. Event payloads are small
// and stable; rendering is deliberately simple.
func Render(eventType, eventID string) Message {
	subject := "Reliastra: " + friendly(eventType)
	text := fmt.Sprintf("Event: %s\nEvent ID: %s", eventType, eventID)
	switch eventType {
	case "incident.created":
		text = "An incident candidate was detected by Reliastra monitoring."
	case "incident.confirmed":
		text = "An incident was confirmed. Evidence is being generated."
	case "incident.resolved":
		text = "The incident has been resolved. Final evidence has been generated."
	case "incident.false_positive":
		text = "The incident candidate was marked as a false positive."
	case "evidence.generated":
		text = "A new evidence artifact is available for download."
	case "monitor.failed":
		text = "A monitor started failing. Reliastra is observing the target."
	case "monitor.recovered":
		text = "A monitor recovered after a failure period."
	default:
		text = fmt.Sprintf("Reliastra event %s (%s)", eventType, eventID)
	}
	return Message{Subject: subject, Text: text, Markdown: strings.ReplaceAll(text, "\n", "\n")}
}

func friendly(t string) string {
	parts := strings.Split(t, ".")
	if len(parts) == 2 {
		return strings.ToUpper(parts[0]) + " " + strings.ReplaceAll(parts[1], "_", " ")
	}
	return t
}
