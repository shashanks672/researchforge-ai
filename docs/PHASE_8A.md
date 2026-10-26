# Phase 8A: Product UI redesign

Phase 8A replaces the developer-style single dashboard with a responsive research
workspace. The redesign keeps the Phase 7 FastAPI and LangGraph contracts, local
provider settings, database records, indexed documents and saved reports in place.
No database migrations or backend architecture changes were made.

## Screens

- `/` is the question composer. It shows the sources that are available, requires a
  ready document selection for document research, and creates then starts a run from
  one button. If saving succeeds but starting cannot be confirmed, the user lands on
  the saved session and is told to check its status before retrying.
- `/research` is paginated history with question search and status filtering.
- `/research/[id]` reloads a saved session, observes its persisted run, displays truthful
  workflow stages, supports cancellation, and presents the report, source passages,
  evidence assessment and Markdown download.
- `/library` supports file selection or drag and drop, upload progress, indexing state,
  filename search, explicit research selection, confirmed reindexing and confirmed
  deletion. Research sessions receive only the selected ready document IDs.
- `/settings` reads the existing system endpoint and presents provider and search
  availability without exposing secrets or offering unsupported controls.

When web search is disabled, the composer explains that state and disables Web and
Documents + web. Local model runs display `LOCAL` and the configured model name. Mock
runs display `DEMO` and synthetic-source labels. The report page does not change saved
execution mode or create a new run when it loads.

## Design and accessibility

The interface uses a warm paper background, white reading surfaces, charcoal text and a
restrained terracotta accent. The token definitions live at the top of
`frontend/src/app/globals.css`; shared controls, cards, status labels, spacing and
responsive breakpoints use those CSS variables and classes. The custom local SVG icons
are in `frontend/src/components/icons.tsx`; there are no remote fonts or image assets.

The layout has a persistent desktop navigation rail and a compact mobile menu. The
mobile shell switches to a vertical layout at 900 px and the question composer adapts
its source choices at 600 px. Reduced-motion preferences disable animation. Pages use
semantic headings and landmarks, a skip link, visible keyboard focus, accessible form
labels, named status messages, native confirmation/source dialogs, keyboard Escape
handling and screen-reader descriptions. The evidence review is collapsed until a
reader asks for its detail; insufficient-evidence findings remain prominent.

The report renderer in `frontend/src/components/markdown-report.tsx` supports the
report formats produced by the backend (headings, paragraphs, lists, quotes, tables,
code and links). A citation is interactive only when its source ID exists in the saved
run's source list. Selecting one opens the stored excerpt and page number in
`CitationDialog`; document citations do not link to fabricated web addresses. Unknown
citation IDs remain visibly unavailable. Link protocols are restricted to HTTP, HTTPS
and mail links.

## API and data flow

The browser still calls the same-origin Next.js routes under `/api`. Those routes proxy
to FastAPI and keep the existing origin checks and response validation. On the home
page, `ResearchComposer` calls `saveSession` from `frontend/src/lib/sessions.ts`, then
`executeRun` from `frontend/src/lib/runs.ts`. It passes the selected document IDs only
for document-based modes. The backend stores the session and run in PostgreSQL and
executes the existing LangGraph workflow.

The report page reads the saved session, saved run, system configuration and stored
verification result. It polls status while the saved run is non-terminal; polling does
not submit work. `useDocuments` polls only while a file is queued, processing or being
removed, including after an upload returns before indexing finishes. Citation buttons
use `run.sources` from the saved record, so the modal shows the passage that was
actually retrieved for that run.

## Verification

The pre-change audit and baseline are recorded in [PHASE_8A_AUDIT.md](PHASE_8A_AUDIT.md).
After implementation, the following checks passed:

- `bash scripts/check.sh`: backend unit tests, frontend lint/format/typecheck/Vitest,
  production build and Compose syntax.
- `backend/.venv/bin/python scripts/test_database.py`: isolated PostgreSQL/Qdrant
  integration tests; the three opt-in local-model tests remain skipped by default.
- `backend/.venv/bin/python scripts/test_database.py --browser`: five Playwright
  workflows using the deterministic mock provider and a disposable database. The flows
  cover setup/source availability, one-click execution, persisted reports and citation
  details, document upload/index/select/research, History, mobile navigation, and
  horizontal overflow at 360, 390, 768, 1024, 1280 and 1440 px.
- Focused Vitest coverage checks that report citations open their saved source, unknown
  citations are not clickable, unsafe links are inert, and document reindexing requires
  confirmation.

The browser suite intentionally uses mock execution so it does not invoke Ollama, paid
providers or a public search service. Phase 7's separate local Documents-mode model test
remains the evidence for real Ollama inference. This UI validation does not claim a new
real-model run or independently rate the generated report.

## Screenshots

The following captures come from the actual Next.js app in Playwright using the local
test backend and real browser rendering. Demo research content is synthetic and labeled
as such. They are not generated mockups.

- [New research, desktop at 1440 px](screenshots/phase-8a/phase-8a-home-desktop.png)
- [New research, mobile at 390 px](screenshots/phase-8a/phase-8a-home-mobile.png)
- [Research History, desktop](screenshots/phase-8a/phase-8a-history-desktop.png)
- [Library with an indexed test document, desktop](screenshots/phase-8a/phase-8a-library-desktop.png)
- [Library with an indexed test document, mobile](screenshots/phase-8a/phase-8a-library-mobile.png)
- [Settings, desktop](screenshots/phase-8a/phase-8a-settings-desktop.png)
- [Saved demo report, desktop](screenshots/phase-8a/phase-8a-result-desktop.png)
- [Evidence review, desktop](screenshots/phase-8a/phase-8a-evidence-review-desktop.png)
- [Document report, mobile](screenshots/phase-8a/phase-8a-result-mobile.png)
- [Document citation drawer, mobile](screenshots/phase-8a/phase-8a-citation-mobile.png)
- [Previously completed local `qwen3:8b` run, desktop](screenshots/phase-8a/phase-8a-existing-local-run-desktop.png). This is a read-only view of the Phase 7 saved run; no inference was started for Phase 8A.

Baseline screenshots are also kept in this folder for comparison.

## Beginner's map

Next.js App Router maps a folder under `frontend/src/app` to a URL. For example,
`frontend/src/app/research/[id]/page.tsx` is the page for one saved research ID. The
page hands that ID to `ResearchScreen`, a client-side React component that can poll the
browser API and respond to clicks.

A design system is the shared set of visual rules used across screens: here, colors,
spacing, cards, buttons, typography and breakpoints. Those rules are in
`frontend/src/app/globals.css`. Reusable components such as `ProductShell`, `Icon`,
`CitationDialog` and `MarkdownReport` keep repeated behavior and visual styles in one
place.

The same-origin Next route in `frontend/src/app/api/sessions/route.ts` receives the
session request and proxies it to FastAPI. The execute route in
`frontend/src/app/api/sessions/[id]/[action]/route.ts` forwards the explicit run mode.
FastAPI's existing research supervisor starts the LangGraph run and saves its state.
The UI checks `/run` until the saved run is complete, then reads its report and
verification artifact. PostgreSQL preserves those records between page visits.

For a first study path, read these files in order:

1. `frontend/src/app/page.tsx` — the home route.
2. `frontend/src/components/research-composer.tsx` — question and source selection,
   session save, and one-click run start.
3. `frontend/src/lib/sessions.ts` and `frontend/src/lib/runs.ts` — browser API clients.
4. `frontend/src/app/api/sessions/route.ts` and
   `frontend/src/app/api/sessions/[id]/[action]/route.ts` — same-origin API proxy.
5. `frontend/src/app/research/[id]/page.tsx` and
   `frontend/src/components/research-screen.tsx` — saved run display and polling.
6. `frontend/src/components/markdown-report.tsx`, `citation-dialog.tsx` and
   `evidence-review.tsx` — report, evidence and citation presentation.
7. `frontend/src/app/globals.css` — shared visual tokens and responsive rules.

## Run locally

Use the existing macOS startup instructions in [README.md](../README.md). The default
commands there start the safe mock configuration. For a real local-model run, use the
already configured Phase 7 local environment and cached Ollama model described in
[PHASE_7.md](PHASE_7.md); that action invokes inference and is separate from the mock
browser checks documented here.
