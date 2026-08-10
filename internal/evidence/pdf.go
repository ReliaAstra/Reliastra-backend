package evidence

import (
	"bytes"
	"fmt"
	"strings"
	"time"

	"github.com/go-pdf/fpdf"
)

// GeneratePDF renders the professional evidence report. PDF generation is
// never part of an incident transaction; it runs in the async outbox
// consumer and the bytes are stored in object storage.
func GeneratePDF(pkg *Package) ([]byte, error) {
	pdf := fpdf.New("P", "mm", "A4", "")
	pdf.SetMargins(20, 18, 20)
	pdf.SetAutoPageBreak(true, 28)
	pdf.AddPage()

	// Header band.
	pdf.SetFillColor(18, 32, 62)
	pdf.Rect(0, 0, 210, 34, "F")
	pdf.SetTextColor(255, 255, 255)
	pdf.SetFont("Helvetica", "B", 20)
	pdf.SetXY(20, 10)
	pdf.Cell(0, 10, "RELIASTRA INCIDENT EVIDENCE")
	pdf.SetFont("Helvetica", "", 10)
	pdf.SetXY(20, 22)
	pdf.Cell(0, 6, "External Dependency Intelligence - Deterministic Evidence Report")

	pdf.SetTextColor(20, 20, 20)
	y := 44.0
	row := func(label, value string) {
		pdf.SetFont("Helvetica", "B", 10)
		pdf.SetXY(20, y)
		pdf.Cell(50, 7, label)
		pdf.SetFont("Helvetica", "", 10)
		pdf.Cell(0, 7, value)
		y += 7.5
	}
	row("Incident:", pkg.Incident.Number)
	if pkg.Service != nil {
		row("Service:", pkg.Service.Name)
	}
	if pkg.Dependency != nil {
		row("Dependency:", pkg.Dependency.Name)
	}
	if pkg.Attribution != nil {
		row("Likely dependency:", pkg.Attribution.DependencyName)
		row("Confidence:", strings.ToUpper(pkg.Attribution.Confidence))
		row("Evidence score:", fmt.Sprintf("%.2f", pkg.Attribution.EvidenceScore))
	}
	row("Started:", formatUTC(pkg.Incident.StartedAt))
	if pkg.Incident.ResolvedAt != "" {
		row("Resolved:", formatUTC(pkg.Incident.ResolvedAt))
	}
	row("Status:", pkg.Incident.Status)
	row("Generated:", formatUTC(pkg.GeneratedAt))
	y += 4

	// Evidence section.
	pdf.SetFont("Helvetica", "B", 13)
	pdf.SetXY(20, y)
	pdf.Cell(0, 8, "Evidence")
	y += 10
	pdf.SetFont("Helvetica", "", 9.5)
	lines := wrap(pkg.Incident.Summary, 95)
	for _, l := range lines {
		pdf.SetX(20)
		pdf.Cell(0, 5.5, l)
		y += 6
	}
	y += 3

	// Correlation factors.
	if pkg.Attribution != nil && len(pkg.Attribution.Explanations) > 0 {
		pdf.SetFont("Helvetica", "B", 13)
		pdf.SetXY(20, y)
		pdf.Cell(0, 8, "Correlation")
		y += 10
		pdf.SetFont("Helvetica", "", 9.5)
		for _, e := range pkg.Attribution.Explanations {
			for _, l := range wrap(" - "+e, 95) {
				pdf.SetX(20)
				pdf.Cell(0, 5.5, l)
				y += 6
			}
		}
		y += 3
	}

	// Measurements table.
	pdf.SetFont("Helvetica", "B", 13)
	pdf.SetXY(20, y)
	pdf.Cell(0, 8, "Measurements")
	y += 11
	pdf.SetFillColor(230, 233, 240)
	table := func(headers []string, rows [][]string) {
		colW := 170.0 / float64(len(headers))
		pdf.SetFont("Helvetica", "B", 9)
		for i, h := range headers {
			pdf.SetFillColor(200, 205, 215)
			pdf.SetXY(20+float64(i)*colW, y)
			pdf.CellFormat(colW, 6, h, "1", 0, "L", true, 0, "")
		}
		y += 6
		pdf.SetFont("Helvetica", "", 9)
		for _, r := range rows {
			for i, c := range r {
				pdf.SetXY(20+float64(i)*colW, y)
				pdf.CellFormat(colW, 6, c, "1", 0, "L", false, 0, "")
			}
			y += 6
		}
		y += 3
	}
	var mrows [][]string
	for _, k := range sortedKeys(pkg.Measurements.Availability) {
		mrows = append(mrows, []string{
			k,
			fmt.Sprintf("%.1f%%", pkg.Measurements.Availability[k]*100),
			fmt.Sprintf("%.0f ms", pkg.Measurements.AvgLatencyMS[k]),
			fmt.Sprintf("%d", pkg.Measurements.TotalObservations),
		})
	}
	if len(mrows) == 0 {
		mrows = append(mrows, []string{"-", "-", "-", "-"})
	}
	table([]string{"Target", "Availability", "Avg latency", "Observations"}, mrows)

	// Regions.
	if len(pkg.Regions) > 0 {
		pdf.SetFont("Helvetica", "B", 13)
		pdf.SetXY(20, y)
		pdf.Cell(0, 8, "Regions")
		y += 11
		var rrows [][]string
		for _, r := range pkg.Regions {
			rrows = append(rrows, []string{
				r.RegionName, fmt.Sprintf("%d", r.Observations), fmt.Sprintf("%d", r.Failed),
				fmt.Sprintf("%.1f%%", r.Availability*100),
			})
		}
		table([]string{"Region", "Observations", "Failed", "Availability"}, rrows)
	}

	// Integrity footer.
	pdf.SetY(-26)
	pdf.SetFont("Helvetica", "B", 8)
	pdf.Cell(0, 4, "Evidence ID: "+pkg.EvidenceID)
	pdf.Ln(4)
	pdf.SetFont("Helvetica", "", 8)
	pdf.Cell(0, 4, fmt.Sprintf("Integrity: %s (recorded in evidence_records) - methodology %s, correlation %s, scoring %s",
		pkg.Integrity.HashAlgorithm, pkg.MethodologyVersion,
		pkg.CorrelationAlgorithmVersion, pkg.ScoringConfigVersion))
	pdf.Ln(4)
	pdf.Cell(0, 4, "RELIASTRA - generated "+pkg.GeneratedAt)

	var buf bytes.Buffer
	if err := pdf.Output(&buf); err != nil {
		return nil, fmt.Errorf("evidence: pdf output: %w", err)
	}
	return buf.Bytes(), nil
}

func formatUTC(s string) string {
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return s
	}
	return t.UTC().Format("2006-01-02 15:04 UTC")
}

func wrap(s string, n int) []string {
	if s == "" {
		return []string{""}
	}
	var out []string
	for _, w := range strings.Split(s, " ") {
		if len(out) == 0 {
			out = append(out, w)
			continue
		}
		if len(out[len(out)-1])+1+len(w) <= n {
			out[len(out)-1] += " " + w
		} else {
			out = append(out, w)
		}
	}
	return out
}

func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	for i := 0; i < len(keys); i++ {
		for j := i + 1; j < len(keys); j++ {
			if keys[j] < keys[i] {
				keys[i], keys[j] = keys[j], keys[i]
			}
		}
	}
	return keys
}
