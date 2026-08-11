# ADR-005: Playwright evidence PDFs

**Status:** Accepted

Evidence needs modern CSS, embedded SVG capability, and deterministic browser rendering. Playwright's Chromium output meets those needs more reliably than limited print-layout engines. Chromium increases the worker image size, so evidence jobs use a dedicated Celery queue that can scale independently. The canonical structured-payload checksum appears inside the document; the final PDF checksum is persisted in immutable metadata because a document cannot embed its own final hash without a self-reference paradox.
