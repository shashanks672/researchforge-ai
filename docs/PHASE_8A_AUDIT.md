# Phase 8A UI audit

Audit date: 2026-10-20. This review was completed before the Phase 8A implementation.

## Verified baseline

- `bash scripts/check.sh`: 153 backend tests and 34 frontend tests passed; lint, format,
  strict type checking and production build passed.
- `backend/.venv/bin/python scripts/test_database.py`: 195 passed, 3 opt-in local-model
  tests skipped. The runner created and removed a fresh `rf_test_*` database and temporary
  Qdrant namespace.
- `backend/.venv/bin/python scripts/test_database.py --browser`: all 5 Playwright tests
  passed using the deterministic mock providers.
- The current local API and UI responded on ports 8000 and 3000. The API was configured
  for local Ollama; no model inference was used for this audit.
- Baseline captures exist locally but are excluded from publication. They show a personal
  display name and a non-synthetic legal document/research history. The public Phase 8A
  screenshots are separate test captures with synthetic content.

## Findings

The app is a single dashboard page, not a product with distinct destinations. Its sidebar
links jump to sections rather than pages, and users cannot open a saved session at a stable
URL. The home screen requires “Save session,” then a history selection, then a separate
research action. That flow exposes backend sequencing instead of helping users start
research directly.

The first screen begins with an engineering-style hero and a full document-management
section before the question composer. It contains phase and milestone labels, an invented
personal workspace/profile, internal workflow language, and test guidance such as “Fake
embeddings.” The public research-mode selector defaults to Web even though this installation
has web search disabled. This could create an avoidable failed run.

Documents are displayed as records with chunk counts and embedding model IDs, and deletion
and reindex controls sit beside every item. Upload is click-only; indexing states and errors
use raw backend terms. There is no dedicated Library, no search, and no focused explanation
of selecting a subset for a run.

Research progress displays raw stage identifiers and detailed plan queries. The report is
rendered in a scrollable monospace `<pre>`, so headings, lists, tables and inline citations
are not readable or interactive. Sources are visible only as expanded raw cards; document
IDs and chunks are primary metadata. The verification panel starts with several expanded
technical sections, exposing method names, fact dimensions, eligibility metadata and
timestamps before a user understands the answer.

History lives below the composer on the same long page. Session IDs and exact timestamps are
shown to ordinary users, and opening an item only updates local state. Empty/loading/error
messages and write protections already exist, but they are distributed through the large
dashboard component. Settings do not have a destination. The existing client components
contain useful abort, timeout, duplicate-submit, polling, schema-validation and safe-proxy
behavior that should be preserved while splitting the UI into routes.

The visual system is inconsistent with the requested direction: cool gray background,
heavy charcoal navigation, small dense labels, monospace status pills, multiple card borders,
and oversized unused header space. At mobile width, desktop navigation wraps into several
rows and the long single-page structure remains. Focus indicators and a skip link exist,
but there are no dedicated source dialogs/sheets, keyboard-operable menu, consistent semantic
status names, or reduced-motion treatment beyond smooth scrolling.

## Existing integration contracts to preserve

- Same-origin Next.js proxy routes expose real FastAPI session, run, document, system and
  verification data. The proxies enforce local host/origin checks and parse/allowlist
  responses; the redesign should use them rather than call FastAPI directly from the browser.
- Session creation is `POST /api/sessions`; a real run begins with
  `POST /api/sessions/{id}/execute`; persisted status comes from
  `GET /api/sessions/{id}/run`. Runs can be cancelled, reports exported, and saved
  verification retrieved through the existing routes.
- Documents can be uploaded, listed, selected, reindexed and deleted through the existing
  local document proxy. Only ready document IDs should be sent in a document-only session.
- The system endpoint supplies truthful provider, model, search and execution-mode status.
  Web and combined modes must be clearly unavailable when search is disabled. Mock output
  must remain labeled as a demonstration; local inference must remain identified as local.
- PostgreSQL owns saved sessions, reports and evidence snapshots. No schema or data
  migration is needed for this UI redesign.
