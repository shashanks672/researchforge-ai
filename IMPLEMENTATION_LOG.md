## 2026-10-19 — Phase 6 implementation

Audited Phase 5 and re-ran the baseline before editing: 136 offline backend tests, 34
frontend tests, 177 PostgreSQL/Qdrant tests and 5 browser tests passed; 2 cached-model
tests were opt-in. Added an explicit sufficiency stage for every planned subquestion,
strict response validation, source-ID checks, categorized answerability outcomes, safe
no-answer reports, and report/UI status disclosure. Empty successful retrieval produces a
citation-free abstention; provider tool failures stay failed. Mock evaluation abstains
rather than claiming synthetic fixtures answer user questions. Follow-up evidence triggers
reassessment and a new draft while the original and every verification snapshot remain
stored.

Added a 6-row development / 12-row held-out synthetic answerability set, a CSV human-review
starter, review guidance, binary answerability/abstention metrics, and a development-only
lexical calibration baseline. Added an opt-in real BGE/Qdrant score study using scratch
PostgreSQL/Qdrant resources, which calibrates semantic, BM25 and hybrid thresholds on the
development split and evaluates the held-out split. Results are saved separately from the
Phase 5 baselines. All answerability labels remain unreviewed; no real LLM quality claim is
made.

Live readiness now requires operator-supplied current input/output token and search unit
prices, explicit server approval, bounded call/token/time/cost controls, pre-dispatch cost
and token reservations, post-response usage accounting, and fail-closed handling when
usage is unavailable. Added a loopback-only `live_smoke_test.py` preflight and separately
approved single-task execution path. Dry run contacted only local readiness/config
endpoints and reported blocked: the active server is in mock mode, local settings are
disabled, credentials/prices/approval are absent, and the configurations do not match.
No live execution occurred. Structured run-stage logs now carry correlation IDs, stage,
provider/model, durations, request and token usage, cost, candidate counts, sufficiency
statuses and safe error codes without question, source or secret contents.

### Phase 6 measurements and verification

- Synthetic lexical held-out set: 12 cases; calibrated threshold 0.1667; accuracy 0.667,
  answerable precision 0.625, recall 0.833, macro F1 0.657, false-answer rate 3/6 (0.50),
  correct abstention 3/6 (0.50), incorrect abstention 1/6 (0.167).
- Retrieval score thresholds on the 12 held-out examples: semantic threshold 0.7196,
  accuracy 0.50 and false-answer rate 4/6; BM25 threshold 6.4567, accuracy 0.583 and false
  answer rate 0/6 but only 1/6 answerable recall; hybrid RRF threshold 0.03279, accuracy
  0.50 and false-answer rate 3/6. These are tiny synthetic results, not production
  settings or calibrated probabilities.
- `bash scripts/check.sh`: 146 backend unit tests and 34 frontend tests passed; Ruff,
  strict mypy, ESLint, Prettier, TypeScript, production build and Compose validation passed.
- `backend/.venv/bin/python scripts/test_database.py`: 187 passed, 3 cached-model
  evaluations skipped by default, using a disposable database and Qdrant namespace.
- `backend/.venv/bin/python scripts/test_database.py --browser`: 5 passed, including
  mock execution, upload/indexing, document-only abstention and mobile layout.
- `RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k phase6_retrieval_threshold_study`: 1 passed using cached BGE and scratch services.
- `backend/.venv/bin/alembic -c backend/alembic.ini check`: no new upgrade operations.
- `backend/.venv/bin/python scripts/live_smoke_test.py --dry-run`: exited blocked as
  expected; no external provider or web request. No model downloads, paid calls, commits,
  pushes, deployment, migrations or destructive development-data operations occurred.

Human review of the 12 held-out questions and an explicitly approved first live test remain
pending. The workspace remains localhost-only. See [Phase 6](docs/PHASE_6.md) and
[evaluation notes](evaluation/README.md).

## 2026-10-19 — Phase 4 completion

Inspected the existing Phase 3 document pipeline and Phase 4 verification workflow before
editing. Phase 3's real PostgreSQL/Qdrant suite passed. The browser baseline exposed an
ambiguous report selector; Phase 4 also lacked its teaching guide and the README,
architecture, security and evaluation overview still described earlier phases. Closed
those gaps, advanced the local schema through additive migration `0004_verification`, and
added end-to-end assertions for uploads being publicly enabled and persisted,
explicitly mock-labelled verification.

Hardened the support boundary: `SUPPORTED` now requires a validated supporting quote from
one of the report claim's cited sources. A model's support label without a supporting
quote, a non-checkable claim labelled supported, or a contradiction without a validated
conflict passage is downgraded conservatively. Added regression cases for irrelevant
citations and unsupported model labels, and updated the hosted assessment prompt and run
prompt revision. Invalid quotes, unknown source IDs, omitted claims, missing report
locations, cross-session evidence and malformed source references still fail the mandatory
stage. The completed report and assessment remain committed atomically.

Verification: `bash scripts/check.sh` passed (108 offline backend tests, 33 frontend tests,
Ruff, strict mypy, ESLint, Prettier, TypeScript, production Next.js build and Compose
validation). `scripts/test_database.py` passed **149 tests with 1 opt-in local-model
evaluation skipped**, against a fresh PostgreSQL database and isolated real Qdrant
collection. `scripts/test_database.py --browser` passed **5 tests**, including real upload,
indexing, document-only research, completed persisted assessment and mobile layout. The
Phase 3 local embedding comparison remains the previously recorded actual six-case run;
CI uses deterministic fake embeddings. Alembic is at `0004_verification`; `alembic check`
found no pending operations. Compose config validated and `npm audit` reported zero
vulnerabilities. Test scratch database/collection were cleaned up. Existing development
rows were preserved; migration `0004` adds only `verification_runs` and its index.

The fixture evaluation has 12 labelled cases and reports measured precision/recall/F1,
false-support rate, citation-support accuracy and latency samples in
`evaluation/phase-4-results.json`. Its recorded 1.0 fixture scores do not measure live
semantic verification quality. No live provider requests, model downloads, commits,
pushes, deployments or new paid services occurred. Qdrant was already running; its ARM64
image is about 73 MB and the observed container used about 151 MiB RAM. The cached
embedding model occupies about 64 MiB. See `docs/PHASE_4.md` for the workflow, limits,
manual demonstration and exact study path.

## 2026-10-19 — Phase 3 completion gate (before Phase 4)

Preserved and verified the actual Phase 2 baseline: 110 backend, 30 frontend, four browser
tests, static checks and production build. Implemented bounded uploads, private atomic
storage, PDF/DOCX/TXT/Markdown parsing, stable page-aware chunks, pinned small CPU
embeddings, fake embeddings for CI, real Qdrant indexing, BM25, RRF, document/combined
research routing, stored document selections and an actual-data document workspace.

Migration `0003_documents` is additive: documents, document_chunks and default-empty
session document IDs. Development migration/check passed; existing sessions retained.
No commits, pushes, paid calls, external account changes or deployment.

Gate results: **124 backend passed, 1 opt-in evaluation skipped** (87 offline + 37 real
PostgreSQL tests); **33 frontend passed**; **5 real browser tests passed** with actual
FastAPI/PostgreSQL/Qdrant and fake embeddings. Ruff/lint/format, strict mypy, ESLint,
Prettier, TypeScript, production build, Compose config and migration checks passed.
The document-only gate checked actual passage text, source provenance and zero web calls.
Generated two-page PDF tests checked exact page references. Screenshot mobile inspected.
Separate opt-in pinned local CPU model evaluation passed and saved actual measurements
in evaluation/phase-3-results.json. All methods scored 1.0 on six easy generated labels;
no hybrid advantage or representative quality is claimed.

Downloaded small MIT BGE ONNX quantized English model (listed 0.067 GB); measured cache
~64 MiB, backend venv ~464 MiB. Qdrant v1.17.1 ARM64 downloaded/started with a 512 MiB
cap. Idle snapshots: PostgreSQL ~81 MiB, Qdrant ~150 MiB, not peak memory benchmarks.
Qdrant storage measured 24 KiB after scratch collection cleanup. Docker became unavailable
during testing, was restarted locally, and real integration tests passed afterward.

Fixed Markdown leading-empty section, historical migration fixture SQL, frontend upload
header normalization and component test isolation; reran checks. Parser processes have
CPU/wall/expansion limits, not a hardened OS sandbox. Snapshots in past reports survive
document deletion. No OCR, multilingual validation, reranker or paid/live calls. Phase 3
passed before Phase 4 implementation began. See docs/PHASE_3.md for teaching and commands.

# Implementation log

## 2026-10-27 — Final GitHub publication preparation (Stage A only)

- Replaced the MIT copyright notice with the author's exact requested line,
  `Copyright (c) 2026 shashank s`. MIT covers original project material; dependency and
  retrieved-source terms remain separate obligations. `evaluation/ATTRIBUTION.md` records
  that bundled web test evidence is original synthetic text, not Wikipedia content. The
  historical acceptance report remains unchanged and describes the prior run accurately.
- Confirmed the connected GitHub account owner as `shashanks672`; the returned owner
  repository pages showed no current `researchforge-ai` name conflict. The local GitHub CLI
  is unavailable, so Git push authentication is not confirmed.
- Prepared `docs/GITHUB_PUBLICATION_ALLOWLIST.txt` with 212 approved paths. It excludes
  private settings and contact data, user uploads and local databases, generated outputs,
  caches, ten older personal screenshots, and two Phase 8A screenshots containing personal
  or private document/history details. The included screenshots were previously reviewed;
  eleven current Phase 8A captures contain synthetic UI or the saved Juniper demo.
- Rechecked manifest paths: 212 unique entries, all present, zero symlinks. Scanned 189
  included text files without printing matched values: no private home paths or private-key
  blocks; credential-pattern matches were limited to local-only database examples, CI
  test configuration, environment-backed settings, and code reading local configuration.
  Email-like strings remain in test fixtures only. Ignored `.env` and `.local/` files were
  not opened. Existing research data was preserved.
- Updated publication instructions and portfolio status with the verified owner, intended
  repository URL, exact metadata, manifest path, and separate proposed create/remote/push
  commands. No external public search, model inference, Git staging, repository creation,
  remote, commit, push, or deployment occurred. Stage B remains unapproved and must not run
  until the user explicitly authorizes it.

## 2026-10-19 — Phase 2

### Scope and baseline verification

- Read the Phase 2 request, existing README, architecture/security/Phase 1 guides, prior
  implementation log, API/database/frontend code, tests and frontend AGENTS guidance.
- Verified actual Phase 1 health/readiness/session history and Next.js public-system
  responses. Reran all **50 backend and 20 frontend baseline tests successfully** before
  implementation. PostgreSQL was healthy, ARM64 dependencies available, about 13 GiB free.
- Reused existing session persistence, request transactions, safe local proxy, test runners,
  design and Docker PostgreSQL. No user session rows were deleted or reset.
- Used official OpenAI documentation for function calling/structured output and primary
  Brave/aiohttp/LangGraph documentation. No model or search-provider calls were made.

### Implemented code

- `backend/app/research/schemas.py`: strict/revalidated plan, subquestion, evidence,
  grounded-statement, report, usage and run contracts.
- `providers.py`: provider protocols, deterministic mock LLM/search, optional OpenAI
  Responses strict planner function + structured report adapter, Brave search/extraction,
  prompt versioning and reported-token/LLM-cost accounting.
- `workflow.py`: typed LangGraph plan/collect/write nodes, insufficient-evidence failure
  route, recursion bound, deduplicated queries/URLs/content, partial-failure warnings,
  source/query tracking and durable application snapshots at meaningful boundaries.
- `web.py`: URL normalization, tracking removal, unsafe address and legacy numeric-form
  rejection, connection-time DNS validation, mixed-answer rejection, manual redirect
  validation, byte/MIME/decompression/time bounds, HTML text extraction and a small lexical
  excerpt-selection baseline. No credentials/cookies/proxies inherited for web retrieval.
- `report.py`: citation-ID membership checks, generated-text escaping, professional
  Markdown sections and references constructed from accepted source metadata.
- `supervisor.py`: one bounded lifespan task, PostgreSQL advisory worker ownership,
  atomic acceptance, unique run/session, cancellation, overall deadline, safe failures and
  interrupted-run recovery without replay. A failed stage cannot commit completed/report.
- `db/models.py`, migration `0002_research_runs`: additive run persistence with plan,
  provenance, report, warnings, usage, model/prompt version and terminal error/timestamps.
  Existing research-session schema/data preserved. Native LangGraph resume is not claimed.
- `api/execution.py`: explicit POST execute (202), GET run, POST cancel and Markdown export.
  Existing session create/list/detail, health/config/readiness remain functional.
- Configuration: disabled default, paired mock/mock or OpenAI/Brave, supported model names,
  backend-only keys, separate live-approval gate, bounds and optional explicit LLM prices.
  Validation hides input values. LangSmith tracing and its pytest plugin are disabled.
- Frontend: existing design plus execution panel, explicit mock/live labels, planning/query
  display, bounded non-overlapping progress polling, cancellation, actual source links,
  escaped Markdown viewer/export, history/status updates and failure states. Shared local
  write/body guards are reused by session and execution proxies.
- Test runner forces child providers disabled for offline tests and mock/mock for browser
  tests, with live approval false. Tests never inherit enabled live execution from callers.
- New Phase 2 guide; README, architecture, security, environment example and historical
  Phase 1 guide updated. Actual mock browser screenshots retained in `docs/screenshots`.

### Commands executed and observed outcomes

| Executed check                                                | Actual result                                                                                                                                                                 |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Baseline PostgreSQL/API + Pytest/Vitest                       | Healthy API/database; 50 backend + 20 frontend passed                                                                                                                         |
| `uv add` LangGraph/OpenAI/aiohttp                             | Installed ARM64-compatible wheels; lock updated; no model downloads                                                                                                           |
| `alembic -c backend/alembic.ini upgrade head`                 | Additive migration applied to development PostgreSQL                                                                                                                          |
| `alembic ... current`                                         | `0002_research_runs (head)`                                                                                                                                                   |
| `alembic ... check`                                           | No new upgrade operations detected                                                                                                                                            |
| `bash scripts/check.sh`                                       | Ruff format/lint, strict mypy, 83 offline tests, ESLint/Prettier/TypeScript, 30 Vitest tests, production build and Compose validation passed                                  |
| `backend/.venv/bin/python scripts/test_database.py`           | **110 backend tests passed**, including 27 real PostgreSQL tests; scratch database removed                                                                                    |
| `backend/.venv/bin/python scripts/test_database.py --browser` | **4 browser tests passed** against production Next.js + real API/PostgreSQL with mock providers only; scratch database removed                                                |
| Hosted provider contract tests                                | Mocked SDK/HTTP methods verified schemas/headers/usage/error handling; no actual service requests                                                                             |
| SSRF tests                                                    | Blocked private/link-local/reserved/multicast/legacy numeric forms; mocked mixed/rebound DNS, unsafe redirects, credential redirects and over-size/encoded responses rejected |
| Durable run/state tests                                       | Pending→running→completed; no-evidence failure; timeout; cancellation; duplicate rejection; competing worker ownership; interruption recovery                                 |
| Migration preservation tests                                  | Phase 1 session preserved across 0001→0002; full rollback/upgrade only in scratch DB; unrelated table preserved                                                               |
| Browser mock demonstration                                    | Explicit start, plan, synthetic source links, completed report, Markdown export and reload persistence verified                                                               |
| Desktop/mobile visual review                                  | Inspected actual browser captures; no horizontal overflow at 390px                                                                                                            |
| `npm audit --prefix frontend`                                 | Zero reported vulnerabilities; no guarantee of security                                                                                                                       |
| `bash scripts/bootstrap.sh` after Phase 2 changes             | Locked dependencies installed successfully; existing database URL preserved                                                                                                   |
| Development DB inspection                                     | Two pending session records, zero research runs; existing questions were not executed                                                                                         |
| Scratch DB inspection                                         | Zero `rf_test_*` databases remained after runs                                                                                                                                |
| Ignore/shell checks                                           | Secrets/dependencies/generated files ignored; bootstrap/check shell syntax valid                                                                                              |

The 110 backend tests comprise 83 database-independent tests and 27 real PostgreSQL tests.
The PostgreSQL runner includes both groups; do not double-count the offline subset.
Reported mock usage is zero provider tokens/cost because no hosted model/search ran.
Tool attempts, stages and elapsed time are actual deterministic execution observations,
not claims about live research quality or performance.

### Problems found, corrected and reverified

- A combined test fixture accidentally started two worker-owning API instances against
  one scratch DB. Split the unrelated tests; added an explicit competing-worker test
  proving a second owner cannot interrupt or execute an active run.
- SQL session advisory locks survive pool rollback. Failed worker initialization now
  invalidates its physical connection; normal shutdown explicitly unlocks before closing.
- Pydantic normally accepts existing model instances without revalidation. Enabled strict
  instance revalidation and tested malformed constructed plans plus unknown citation IDs.
- Polling initially risked dropping the parent status callback when a terminal update
  cleaned up the effect. Fetch terminal session state before updating the run, and test
  that completion refreshes the parent. Polling deadlines no longer reset at every stage.
- Security review confirmed `ipaddress.is_global` can be true for multicast addresses.
  Added explicit multicast/reserved checks and regression cases. Also reject noncanonical
  decimal/octal/hex IPv4 forms at the application boundary and quote unsafe URL-path bytes.
  The installed aiohttp also guards legacy numeric IPv4 forms; application checks are explicit.
- Added separate planning/writing snapshots and disclosures for source/query limits;
  source collection stops when enough sources are collected rather than making extra calls.
- Resolved lint/type findings and reran all required checks. Playwright's inherited
  NO_COLOR/FORCE_COLOR warning remains harmless runner output.

### Resource observations, limits and stop boundary

- About 13 GiB disk remained. The backend environment measured approximately 246 MiB;
  frontend dependencies approximately 526 MiB. These are disk snapshots, not memory benchmarks.
- Existing single PostgreSQL container reused; no Qdrant, Redis, Celery, GPU libraries,
  large models, datasets or extra persistent database technologies introduced.
- **Hosted OpenAI/Brave calls remain unapproved and unverified.** Account/model availability,
  real extraction quality, live usage and provider costs still need an approved live test.
- Citation IDs are validated, not semantic claim truth. No retrieval/answer-quality scores,
  model comparisons or provider latency benchmarks were invented.
- No native resumable graph checkpoints, document upload/RAG, Qdrant, hybrid retrieval,
  advanced verification, PDF export or public deployment. Authentication and hosted CI
  remain future/unverified. No commits or pushes were performed.
- Phase 2 implementation and the entire mock path are locally verified. Stop at Phase 2.

### Local inspection handoff

Restarted the owned native API with explicit process-only `mock/mock` providers and live
approval false, then started Next.js on loopback. Actual `/health`, `/ready`, Next.js
`/api/system` and history requests returned 200. Public config identifies mock mode;
the two saved development sessions remain pending and no runs were seeded into them.
Both services are left running for inspection, subject to the local tool-session lifetime.
The ignored `.env` was not changed to enable live providers. Use the Phase 2 guide to
restart, reload the dashboard, choose Web and explicitly start a mock demonstration.

## 2026-10-19 — Phase 1

### Scope and Phase 0 baseline

- Read the Phase 1 request and the existing README, architecture, security, Phase 0
  walkthrough, sources, tests and configuration. Preserved the existing design and modules.
- Verified actual 200 responses from `/health`, `/api/v1/config` and the Next.js
  `/api/system` proxy before edits. Existing **20 backend + 6 frontend tests passed**.
- Confirmed local Git branch `main` has no commits, no changes were committed/pushed,
  and `.env`, `.env.local`, virtual environments, dependencies and generated files are ignored.
- Docker daemon available on ARM64; PostgreSQL image already cached. About 14 GiB disk
  available at inspection. SQLAlchemy/Alembic had not been installed in Phase 0.

### Implemented

- SQLAlchemy 2.0.55 async ORM with psycopg 3.3.6 and Alembic 1.20.0; updated `uv.lock`.
- Lifespan-managed three-connection pool, independent request sessions, explicit transaction
  boundaries, rollback on failure, sanitized database errors, connect/pool/statement limits.
- Private `RF_DATABASE_URL` as a redacted setting. Bootstrap appends a URL derived from
  existing Compose configuration only when absent; credentials are not printed.
- `research_sessions` with UUID, server-selected workspace, question, mode, status,
  UTC timestamps and nullable error field. Database constraints and a history index.
- Explicit migration `0001_sessions`; startup never creates tables. Migration autogeneration
  excludes unrelated tables. No development data was deleted or reset.
- `POST /api/v1/research/sessions` (201 pending), list with bounded pagination and stable
  timestamp/UUID ordering, and UUID detail (200/404/422 as appropriate).
- `/ready` checks schema revision and readable session columns; `/health` remains process
  liveness. Public config reports Phase 1/session capability without revealing credentials.
- Same-origin Next.js create/list/detail proxies with local Host/Origin checks, JSON and
  byte limits, fixed upstream paths, timeouts, sanitized failures and allowlisted fields.
- Existing dashboard now has an interactive question/mode form, save/loading/error states,
  saved history, pagination, detail/status refresh, empty states and responsive layout.
- Tests create their own fresh `rf_test_*` PostgreSQL databases. Browser tests run separate
  servers on 3100/8100 and refuse to reuse development services or databases.
- Extended CI with PostgreSQL, database tests and isolated browser tests. Hosted CI has
  not run; an authorized GitHub push is still required.
- Updated README, architecture, security, migration notes and new `docs/PHASE_1.md` teaching
  guide. Captured and visually inspected real desktop/mobile browser-test screenshots.

### Important changed files

- Backend: `app/db/{models,session}.py`, `app/schemas/sessions.py`,
  `app/services/sessions.py`, `app/api/{sessions,system}.py`, `app/main.py`,
  `app/core/config.py`, `app/schemas/system.py`, `pyproject.toml`, `uv.lock`.
- Migrations: `backend/alembic.ini`, `backend/migrations/env.py`, revision and template.
- Frontend: `session-workspace.tsx`, page integration and additional CSS; session types,
  backend/proxy helpers, create/list/detail route handlers and public-system contract.
- Tests: new boundary, real PostgreSQL and process persistence tests; frontend form/proxy
  tests and expanded browser workflow; corresponding regression assertions updated for Phase 1.
- Operations: bootstrap/check scripts, local URL configuration helper, disposable database
  test runner, Compose comments, environment example and CI workflow.

### Executed checks and actual results

| Command/check                                                         | Result                                                                                                                        |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Baseline health/config/frontend HTTP requests                         | 200 from actual running Phase 0 services                                                                                      |
| Baseline Pytest + Vitest                                              | 20 + 6 passed before Phase 1 edits                                                                                            |
| `uv add` with SQLAlchemy async, psycopg binary, Alembic               | ARM64 install succeeded; lock updated                                                                                         |
| `bash scripts/bootstrap.sh` after Phase 1 changes                     | Locked dependencies installed; existing private database URL preserved                                                        |
| `docker compose --profile infrastructure up -d --pull never postgres` | Cached image used; healthy local container; Qdrant not started                                                                |
| `alembic -c backend/alembic.ini upgrade head`                         | Migration applied successfully to development database                                                                        |
| `alembic -c backend/alembic.ini current`                              | `0001_sessions (head)`                                                                                                        |
| `alembic -c backend/alembic.ini check`                                | No new upgrade operations detected                                                                                            |
| `backend/.venv/bin/python scripts/test_database.py`                   | **50 passed** against an isolated real PostgreSQL DB; scratch DB cleaned up                                                   |
| `bash scripts/check.sh`                                               | Ruff lint/format, strict mypy, 33 offline tests, frontend lint/format/types/tests, production build and Compose config passed |
| Final frontend checks after origin correction                         | Lint/types/build passed; **20 Vitest tests passed**                                                                           |
| `backend/.venv/bin/python scripts/test_database.py --browser`         | **3 browser tests passed** using production Next.js, actual FastAPI and PostgreSQL                                            |
| Actual API subprocess stop/restart test                               | Same UUID, question, status and timestamps retrieved after first process terminated                                           |
| Disposable migration downgrade/upgrade                                | Session table removed/recreated only in scratch DB; unrelated sentinel data preserved; readiness 503 without schema           |
| Real database constraint and write-failure tests                      | Invalid status rejected by PostgreSQL; failed flushed write rolled back; next request succeeded                               |
| Real refused-connection check                                         | Readiness and session APIs 503 while health stayed 200                                                                        |
| Development database inspection after test runs                       | Migration at head; zero development sessions; test records stayed isolated                                                    |
| Scratch database cleanup inspection                                   | Zero `rf_test_*` databases remained after the final browser run                                                               |
| `npm audit --prefix frontend`                                         | Zero reported vulnerabilities; not a security guarantee                                                                       |

The 50 backend tests comprise 33 database-independent tests and 17 PostgreSQL tests.
The database runner executes both groups; the ordinary check script deliberately excludes
database tests so offline verification works. There are no paid API calls or LLMs in tests.
Browser tests cover save/detail/reload persistence and desktop/mobile layout. Timestamps
are stored and returned in UTC; the browser presents them in its local time zone.

### Problems found and fixed, with reruns

- Alembic initially proposed removing an unrelated sentinel table during autogeneration.
  Added a managed-table include filter; the real downgrade/upgrade and schema check passed.
- Browser save initially returned 403 because Next.js can normalize its internal request
  URL hostname. Validate the incoming loopback Host and compare it with browser Origin,
  while rejecting remote hosts/cross-site writes. Added a regression unit test; all
  frontend tests, production build and real browser save/reload tests passed afterward.
- One immediate-resize full-page screenshot had capture artifacts. Reloaded at the mobile
  viewport and reset scroll before capture; reran all browser checks and inspected the
  corrected desktop/mobile images. No application layout rewrite was needed.
- Corrected formatting/type findings during development and reran the relevant checks.
- Playwright's inherited NO_COLOR/FORCE_COLOR warning remains harmless test-runner output.

### Resource observation and limits

- A single `docker stats --no-stream` observation showed PostgreSQL at about 99.8 MiB
  against its 512 MiB cap and 0.05% CPU. This is an idle snapshot, not a performance benchmark.
- About 13 GiB disk remained. No models, datasets, additional database technologies, Qdrant process,
  paid providers, public deployment, commits or pushes were introduced.
- Authentication is not implemented. All application and database ports stay on loopback.
- Sessions remain pending; document/combined modes save intent only. No cancellation,
  status mutation, live research, report generation or uploads exist in Phase 1.
- Writes have no idempotency key: after a lost response, inspect history before retrying.
  Offset pagination can shift when new rows arrive. Multi-user authorization, full app
  containers and hosted CI execution remain unverified/future work.

**Phase 1 functionality is verified locally. Stop here; Phase 2 is not implemented.**

### Inspection handoff

The native frontend was restarted after verification and the local API/database remain
running. Actual development requests through Next.js `/api/system` and `/api/sessions`
returned 200, with empty development history. Open `http://127.0.0.1:3000` and save your
own question. These processes depend on the local tool session; use the Phase 1 guide
to restart them if needed. No test records were seeded into your development workspace.

## 2026-10-19 — Phase 0

### Inspection and boundaries

- Empty workspace; no existing Git repository or AGENTS.md instructions found.
- Initialized a local `main` branch with `git init -b main`; no commits or remotes added.
- macOS 27.0.1, ARM64, 16 GiB unified memory; about 13 GiB disk available before setup.
- Default Python 3.14.0; selected installed Python 3.12.14.
- Node 22.19.0, npm 10.9.3, Git 2.54.0, Docker 29.7.2, Compose 5.4.0.
- Docker daemon running on aarch64 with 8,319,504,384 bytes VM memory.
- Google Chrome installed; `code` launcher not found.
- No paid calls, models, datasets, new container images, public deployment, Git commits
  or pushes authorized or performed. Scope is Phase 0 only.

### Features and files

- `backend/app`: application factory, local settings, JSON request metadata logs, health,
  explicit public config and bounded initial research contracts.
- `backend/tests`: API, config, host/CORS and request validation tests.
- `frontend/src`: responsive workspace with honest disabled research controls, same-origin
  server health proxy, live connection card, failure and retry states.
- `frontend/tests`, `frontend/e2e`: component/proxy tests and real browser/API smoke checks.
- Python and npm manifests/locks, formatting/type-check configs, environment examples,
  bootstrap/check scripts and VS Code configuration.
- Opt-in infrastructure-only Compose definition and GitHub Actions checks.
- README, architecture, security, phase guide, migration/evaluation placeholders and MIT license.
- Actual desktop and mobile screenshots in `docs/screenshots`, captured during real
  browser/API tests and visually inspected.

### Commands and outcomes

**Phase 0 foundation checks passed on the inspected Mac.**

| Executed command                                                                    | Observed result                                                                                                          |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `python3.12 -m venv backend/.venv` and bootstrap uv installation                    | Successful isolated ARM64 environment                                                                                    |
| `backend/.venv/bin/uv lock --project backend --python /opt/homebrew/bin/python3.12` | Resolved and locked Python dependencies                                                                                  |
| `backend/.venv/bin/uv sync --project backend --locked`                              | Successful installation from lock                                                                                        |
| `bash scripts/bootstrap.sh`                                                         | Successful environment setup and locked npm install; environment files ignored by Git                                    |
| `bash scripts/check.sh`                                                             | Exit 0: Ruff lint/format, strict mypy, Pytest, ESLint, Prettier, TypeScript, Vitest, production build and Compose syntax |
| Pytest (within check script)                                                        | **20 passed**, no warnings on final run                                                                                  |
| Vitest (within check script)                                                        | **6 passed** across 2 test files                                                                                         |
| `npm run build` (within check script)                                               | Next.js production build succeeded; `/`, `/_not-found`, `/api/system` generated                                          |
| `(cd frontend && npm run test:e2e)`                                                 | **2 passed** using installed Google Chrome and actual production Next.js + FastAPI servers                               |
| `npm audit` / lockfile install audit                                                | **0 reported vulnerabilities** in selected dependency graph; not a guarantee of security                                 |
| `docker manifest inspect postgres:16-alpine`                                        | ARM64 manifest present; no image download                                                                                |
| `docker manifest inspect qdrant/qdrant:v1.17.1`                                     | ARM64 manifest present; no image download                                                                                |
| `docker compose --env-file .env.example --profile infrastructure config --quiet`    | Valid configuration; containers not started                                                                              |
| `bash -n scripts/bootstrap.sh scripts/check.sh`                                     | Shell syntax valid                                                                                                       |
| `git check-ignore .env frontend/.env.local backend/.venv frontend/node_modules`     | All four paths ignored                                                                                                   |
| Documented Uvicorn reload command and `npm run dev`                                 | Both native development servers started successfully on local ports 8000/3000                                            |
| `curl --fail --silent http://127.0.0.1:8000/health`                                 | Actual 200 JSON health response from development server                                                                  |
| `curl --fail --silent http://127.0.0.1:3000/api/system`                             | Actual 200 JSON public status through development Next.js proxy                                                          |

The browser smoke tests confirmed an actual `200` response through the Next.js proxy,
correct backend identity, disabled research submission, and no horizontal overflow at
390px width. Component tests cover failure display and retry; proxy tests cover public
field allowlisting, sanitized errors and rejection of nonlocal backend targets.

Final selected versions include Python 3.12.14, FastAPI 0.146.0, Pydantic 2.14.1,
uv 0.13.1, Next.js 16.4.2, React 19.3.1, Tailwind 4.3.3 and TypeScript (see npm lock).
The environment measured about 153 MiB for the backend virtual environment and 526 MiB
for installed frontend dependencies; roughly 12 GiB disk remained. These are disk
observations, not runtime memory benchmarks.

### Problems found and corrections verified

- Initial Python formatting/type checks found a long assertion and an unnecessary ignore;
  corrected and reran Ruff, mypy and Pytest successfully.
- Current Starlette deprecated its httpx test-client path. Switched the development
  dependency to supported httpx2 and reran all 20 backend tests without the warning.
- Initial Next.js ESLint configuration pulled in an advisory-affected `braces` chain
  without a patched release. Replaced that development configuration with supported
  ESLint 10, TypeScript ESLint and React Hooks rules. No audit suppression or forced
  downgrade was used; the resulting install audit reports zero vulnerabilities.
- React Hooks lint caught state-setting through an effect helper. Moved network probing
  outside the component and update state from its asynchronous completion; lint,
  component behavior tests and browser tests all passed afterward.
- Added ESM package mode and an explicit Turbopack root to remove configuration warnings
  and prevent inference from an unrelated parent lockfile. Final checks/build passed.
- Playwright reported a non-blocking inherited `NO_COLOR`/`FORCE_COLOR` environment
  warning; browser behavior passed. No application warnings remained in the final checks.
- `next dev` generated `frontend/AGENTS.md` with framework guidance. Read it and retained
  it as generated; its formatting check passes. Future Next.js changes should consult
  the installed version's documentation as it instructs.

### Local inspection state

The native development servers were left running on `127.0.0.1:8000` and
`127.0.0.1:3000` for inspection. Their process lifetime depends on the local tool session;
the documented commands restart them if needed. Start commands bind only to loopback.
Uvicorn watches only `backend/app` to avoid scanning frontend dependencies on this Mac.

### Outstanding work

No database schema, research execution, live search, LLM provider, upload pipeline,
embeddings, hybrid retrieval, verification, report export, authentication or quality
benchmark is implemented. Do not confuse liveness with dependency readiness. Container
runtime, clean Linux installation and hosted GitHub Actions behavior remain unverified.
Full application Dockerfiles belong to Phase 6. No quality scores or memory/latency
benchmarks have been claimed. Next is Phase 1: introduce SQLAlchemy, Alembic, PostgreSQL
readiness, persistent request creation and history before adding actual research agents.

# 2026-10-19 — Phase 5: evaluation and reliability

### Baseline and scope

- Audited the existing Phase 3–4 architecture, retrieval, claim verifier, tests, and
  evaluation artifacts before edits. `bash scripts/check.sh` baseline: 108 backend tests
  passed, 33 frontend tests passed; lint, type checks, formatting, production build, and
  Compose validation passed.
- Preserved `evaluation/phase-3-results.json` (six generated records) and
  `evaluation/phase-4-results.json` (12 controlled fixtures) as earlier regression
  baselines. Neither is a broad quality benchmark.
- No hosted model, search call, paid API, model download, commit, push, or deployment.

### Implementation

- Added deterministic claim eligibility categories and reasons. Incomplete clauses,
  opinion/question/instruction text, and context-dependent pronouns are retained in the
  verification audit record but cannot pass the checkable gate. Original claim text is
  preserved; no missing antecedent is invented.
- Added explicit regression cases for the observed “In addition, it has” and “The body of
  research” failures, plus pronoun context, supported and contradicted claims, negation,
  number/date cases, multi-passage claims, questions, opinions and citation mismatch.
- Added pure retrieval metric code and unit tests for Recall/Precision@K, MRR, nDCG,
  no-answer queries, missing/deleted IDs, unknown and duplicate results, and sample-size
  gated p95 latency.
- Added a 16-passage/20-query synthetic retrieval dataset and an opt-in local benchmark
  using the cached embedding model, actual Qdrant and the existing BM25/hybrid path.
- The verification panel now shows verdict counts, filters by verdict and collapses claim
  details until opened. Eligibility reasons and exact evidence quotes remain inspectable.
- Added Phase 5 implementation and annotation documentation. The dashboard UI is deferred;
  reproducible CLI JSON reports cover this local evaluation scope.

### Current evaluation status

- Eligibility: 12 synthetic provisional cases; observed regression fixture results are
  saved under `evaluation/results/phase-5-eligibility.json`.
- Verification: 18 synthetic provisional cases; deterministic mock metrics and raw
  predictions are in `evaluation/results/phase-5-verification.json`.
- Retrieval: the opt-in run indexed 16 short passages and evaluated 20 queries (17
  answerable, 3 no-answer) on Apple M4, Python 3.12.14, BGE small English ONNX CPU and
  local Qdrant. Recall@3 was 0.941 semantic, 0.882 BM25, 0.941 hybrid; MRR was 0.897,
  0.847 and 0.924 respectively. At K=10, all three methods recalled all labelled
  answerable passages. Median query latency was 18.20 ms semantic, 2.76 ms BM25, 18.67
  ms hybrid. Two fresh indexes produced identical rankings and metric scores after stable
  tie-breaking. Every method returned results for all no-answer queries, so the empty-
  result rate was 0%; answerability thresholding is absent. Results and raw measurements
  are in `evaluation/results/phase-5-retrieval.json`.
- No human review or live model evaluation has occurred. Exact and narrow relation-based
  mock support is not semantic entailment or factual truth.
- Final `bash scripts/check.sh`: **136 backend unit tests and 34 frontend tests passed**;
  Ruff, strict mypy, ESLint, Prettier, TypeScript and production build passed. The isolated
  PostgreSQL/Qdrant runner passed **177 tests; 2 opt-in local-model cases were skipped by
  default**. The five browser integration tests passed. The Phase 5 retrieval benchmark
  was run separately twice on the already cached model; both rankings and aggregate
  metrics matched. `alembic check` reported no pending operations; Compose config passed.
- Tests used unique scratch databases and Qdrant namespaces, then removed those test
  resources. Development records were preserved. No paid or hosted calls, commit, push,
  deployment, or new model download occurred.

## 2026-10-19 — Phase 7: local LLM and bounded free search

- Reused the already cached Ollama `qwen3:8b` model; no model/runtime was downloaded or
  installed. Added a loopback-only structured provider, a separately labelled local run
  mode, fact-level evidence quotations, and opt-in English Wikipedia search guarded by a
  contact address and explicit setting.
- Added fresh synthetic v2 development and final sets. The development split informed a
  conflict-prompt clarification; the final split was then frozen and run once. It recorded
  5 valid decisions / 6, 0 false answers / 4 unanswerable, 3 correct abstentions / 4,
  2 / 2 answerable recall, 5 / 6 accuracy and 0.75 macro F1. One conflict response failed
  consistency validation on both bounded attempts. All four quotes from accepted outputs
  passed source-ID and exact-text validation; this does not prove entailment. Labels remain
  provisional and no human review is claimed. See `evaluation/results/phase-7-ollama-
answerability-v2.json`.
- The user chose to skip the public search test; zero external search calls were made.
  Local answerability evaluation used the cached model only. The complete Documents-mode
  local model workflow and opt-in real-model browser test remain unverified.
- Final offline checks: 151 backend unit tests and 34 frontend tests passed; Ruff, strict
  mypy, frontend lint/format/typecheck and production build passed. The isolated
  PostgreSQL/Qdrant suite passed 192 tests with 3 opt-in model tests skipped. All 5
  deterministic browser tests passed. Scratch databases were removed; development data
  was preserved.

### Local Documents-mode acceptance follow-up (2026-10-19)

The prior “not yet run” status above was accurate when the original Phase 7 work ended.
This follow-up completes the requested local-model acceptance check without starting
Phase 8:

- Reused cached Ollama `qwen3:8b` and cached local BGE embeddings, existing PostgreSQL and
  Qdrant volumes, and a two-page synthetic PDF. Search was disabled. No public/paid calls,
  model downloads, commits, pushes or deployments occurred. Existing documents and sessions
  were preserved; only the test document and demonstration sessions were added.
- Answerable run: session `[saved record ID omitted]`, run
  `[saved record ID omitted]`, completed LOCAL with the exact page-1 document
  passage cited. It used five model calls across planning, sufficiency, report writing,
  claim extraction and claim assessment; took 89.142 s total, reported 60.888 s inference,
  1.074 s load time, and 4,089 input / 1,121 output tokens. It made zero search/fetch calls
  and reported zero cost.
- Unanswerable run: session `[saved record ID omitted]`, run
  `[saved record ID omitted]`, completed LOCAL with `INSUFFICIENT`, an explicit
  no-answer report and no invented maintenance cost. It used two model calls (planning and
  sufficiency), took 25.739 s, and reported 1,444 input / 307 output tokens. Deterministic
  abstention text replaced model report writing; claim extraction and verification were
  skipped because no factual answer was produced. It made zero search/fetch calls and
  reported zero cost. The UI and persisted records both labelled the run LOCAL / `qwen3:8b`.
- A repeated answerable run failed during verification (`verification_failed`), even after
  succeeding through prior stages; the complete successful pair above establishes the
  acceptance path but not repeatability. One earlier answerable response contained a
  supported fact and exact quote while its redundant aggregate status contradicted them.
  Ollama/OpenAI adapters now derive aggregate fields from validated fact-level assessments;
  quote/source checks remain intact. The planner prompt now keeps single-fact questions
  atomic. Document-only local abstentions skip unnecessary claim-model calls, and report
  references now display “document passage” instead of “web source.” Focused tests cover
  these changes; mock web verification and document conflict/stale-evidence checks still
  run through the regular verifier.
- Before inference, disk had 11 GB free and system memory was 78–81% free. During inference
  free memory fell to 25–26% with Ollama using about 6.2–6.5 GB; it recovered to 64–70% after
  stopping the model. Disk remained at 11–12 GB free. These observations were safe for the
  completed runs but leave limited free disk for unrelated work.
- After the integration fixes: `bash scripts/check.sh` passed with 153 backend unit tests
  and 34 frontend tests; Ruff, strict mypy, ESLint, Prettier, TypeScript and production
  build passed. The disposable PostgreSQL/Qdrant suite passed 195 tests with 3 opt-in local
  model tests skipped; all 5 deterministic browser tests passed. Scratch databases and test
  namespaces were removed.
- Exact Mac reproduction steps, questions, source/page checks and cleanup commands are in
  `docs/PHASE_7.md` under “Verified local Documents-mode demonstration.” The optional
  automated real-model browser test and public search test remain unrun; the local UI was
  manually inspected for the successful local sessions.

## 2026-10-20 — Phase 8A: product interface redesign

- Audited the old single-page dashboard and recorded the verified baseline and user-facing
  issues in `docs/PHASE_8A_AUDIT.md` before changing the frontend.
- Replaced the developer-oriented dashboard with dedicated New research, History,
  Library, Settings and saved-report routes. One-click research still uses the existing
  session-save and execute endpoints. Session, run, report, verification, document and
  system data continue through the existing same-origin Next.js proxies.
- Added a consistent warm-light design system, responsive navigation, accessible
  controls/dialogs, safe Markdown rendering, citation-to-saved-passage details, a less
  dominant evidence review, truthful stage labels and visible LOCAL/DEMO distinctions.
  Added confirmed reindexing for ready files and kept explicit document selection.
- Fixed document-status polling so an upload continues to update from queued through
  indexing to ready even when the initial empty library response happened first. Fixed
  the mobile shell's horizontal layout and verified no overflow at 360, 390, 768, 1024,
  1280 and 1440 px.
- Added `docs/PHASE_8A.md` with route behavior, API data flow, screenshots, reproduction
  boundaries and a beginner-oriented study map. Updated the README and this log.
- Frontend/browser checks use deterministic mock providers and isolated test resources.
  No local model inference, public search, paid provider call, model download, migration,
  user-data cleanup, commit, push or deployment was performed for this UI work.
- Final checks: `bash scripts/check.sh` passed: 153 backend unit tests and 36 frontend tests, plus lint, formatting, strict typecheck, production build and Compose validation. The isolated PostgreSQL/Qdrant suite passed 195 tests with 3 opt-in cached-model evaluation cases skipped. All 5 deterministic Playwright tests passed, including upload-to-ready, saved citation passage, history navigation and no horizontal overflow at six viewport widths. Screenshots were refreshed from this run under `docs/screenshots/phase-8a/`.

## 2026-10-20 — Free Web and Combined-mode audit

- Audited the Phase 7 Wikipedia adapter and provider configuration. The existing
  `ollama/wikipedia` combination is wired through the existing LangGraph workflow; Web
  mode uses Wikipedia sources and Combined mode retrieves selected documents before the
  same web collection stage. Document and web provenance are preserved separately.
- Added offline integration tests that exercise the actual adapter and full graph with
  mocked HTTP responses. The Combined case verifies document ID/page metadata alongside
  the Wikipedia article URL, excerpt and content hash. A disabled-provider test confirms
  the run fails closed without synthetic-source substitution. No public HTTP request is
  made.
- Tightened the operator-contact setting to reject malformed HTTPS/mailto values and
  header control characters. Added the configured contact to both API and article-fetch
  User-Agent headers and paced both request types through the adapter's one-second limit.
- Clarified the disabled-state UI and Settings copy, documented the English-Wikipedia-only
  scope, contact and usage requirements, and added an applicable-license reminder. The
  README and `.env.example` no longer imply that mock Web fixtures are public search.
- `bash scripts/check.sh`: 160 backend unit tests and 38 frontend tests passed; Ruff,
  strict mypy, ESLint, Prettier, TypeScript, production build and Compose validation passed.
  PostgreSQL/Qdrant tests passed 202 with 3 opt-in model evaluations skipped. All 5 browser
  tests passed. Public search remains disabled and was not tested live because the actual
  operator contact is not configured and no live request was authorized in this task.
  Web and Combined are integration-ready but are not marked end-to-end verified.

## 2026-10-21 — Local setup and Web activation workflow

- Audited the running Mac services without exposing environment values. Docker Desktop
  29.7.2, the repository's PostgreSQL 16 and Qdrant containers, Ollama with cached
  `qwen3:8b`, FastAPI and Next.js were already healthy. PostgreSQL was at migration head
  `0005_local_providers`; Qdrant had one collection, the workspace had two ready indexed
  documents and 16 saved sessions. Existing records and files were not changed.
- The active API reported `execution_mode=local`, model `qwen3:8b`, and hosted calls
  disabled, but `search_provider=disabled`; no private Wikimedia contact was available
  to this process. No contact was invented, exposed, or stored, and no public request was
  made. Thus Documents is available; Web and Documents + Web remain unavailable pending
  the operator's private configuration and a later bounded live test.
- Added macOS helpers: `scripts/start_local.sh` starts/reuses checked local services and
  uses Docker Compose `--pull never`; `scripts/configure_wikipedia_contact.sh` accepts a
  real contact with hidden terminal input and saves it only under ignored `.local/` with
  owner-only permissions; `scripts/restart_local_api.sh` verifies project ownership and
  idle workflow state before a graceful API restart; `scripts/stop_local.sh` stops only
  recorded helper-started API/UI processes and never stops databases or Ollama. No
  startup agents were installed. Added README and Phase 7 instructions.
- Startup was executed successfully after correcting a boolean-case comparison found by
  the first run. It reused the verified API PID 2168 and UI PID 1918, confirmed the
  PostgreSQL/Qdrant containers healthy, reported `LOCAL qwen3:8b`, and kept search
  disabled. It did not replace user-managed processes. The live readiness/config endpoints
  also confirmed `ready`, database `ok`, and no paid-hosted calls. Before this work, disk
  had 14 GiB free and memory pressure reported 61% free; no model inference or public
  query was executed.
- Validation after the change: `bash scripts/check.sh` passed 160 backend tests and 38
  frontend tests, Ruff, format checks, strict mypy, ESLint, TypeScript, production build
  and Compose syntax. The isolated PostgreSQL/Qdrant suite passed 202 tests with 3
  opt-in cached-model tests skipped and removed only its unique scratch database. The
  browser suite passed all 5 Playwright tests and removed only its scratch database.
  Shell syntax and contact-validator edge checks passed. Existing browser coverage includes
  the composer, library upload/document mode, saved report citation, history, and responsive
  layout; Settings is covered by frontend component tests rather than a standalone browser
  flow. No model download, paid call, public search, data deletion, commit, push or deploy
  occurred. Live Web and Combined behavior remains unverified pending private setup and
  explicit approval for the two requested tests.

## 2026-10-22 — Private Wikimedia contact input fix

- Fixed the contact validator and setup prompt to accept an ordinary email address and
  normalize it to `mailto:…`; existing `mailto:` and HTTPS contact pages remain supported.
  Invalid input now gives a generic format hint without echoing the submitted value. The
  private setup command requires a controlling terminal before prompting, so it cannot
  fall back to an echoing stdin prompt.
- Added fake-address unit cases for all accepted formats and invalid-input errors, including
  an assertion that rejected contact values do not appear in validation output. The
  operator then entered their contact in the hidden Terminal prompt; the file is ignored
  and has mode 600, and the API reports Wikipedia enabled. The contact value is not
  recorded here. No external request was made.
- Docker Desktop had stopped between sessions. Opened the installed Docker Desktop app,
  started the existing database containers without pulling images, and launched the
  application through a persistent Terminal session. Loopback readiness returned
  `ready`, the UI returned HTTP 200, and the API reported LOCAL `qwen3:8b`, search disabled,
  and hosted calls off. No public request or model inference occurred.

## 2026-10-22 — Live research reliability remediation (offline)

- Added atomic per-run limits for search, article fetches, redirects and failed attempts,
  plus an optional process-wide cap. Budget exhaustion is persisted as a safe workflow
  error with usage counters; article text is capped and truncation is recorded. External
  HTTP retries are configured separately from bounded local-model output repair.
- Reproduced the local Qwen sufficiency failure using previously saved Wikipedia evidence:
  the response schema was valid, but quoted passages were not exact source substrings.
  Tightened the prompt and added one repair-specific retry while retaining exact quote,
  source ID and fact validation. No validator was weakened.
- Changed small-corpus passage ranking to BM25Plus after the Juniper capacity passage
  ranked below an irrelevant page. Combined retrieval now selects a broader candidate set
  and reserves a source slot for web evidence; regression coverage checks document page
  metadata and real web provenance.
- Offline verification passed: `bash scripts/check.sh` (176 backend and 38 frontend tests,
  lint, formatting, type checks and production build); isolated PostgreSQL/Qdrant tests
  (220 passed, 3 optional cached-embedding cases skipped); and all 5 Playwright tests in
  mock mode. `git diff --check` passed. Test resources were isolated and removed by the
  test harness; saved user sessions and documents were not modified.
- Two in-memory Web/Combined runs with cached Qwen reached sufficiency but failed before
  report generation. The dedicated repair prompt was added afterward and has only been
  exercised in offline regression tests; local inference was paused at the user's request
  after a usage-limit interruption. No local document-to-report acceptance, final citation
  check, claim verification, or persisted LOCAL Web/Combined UI result is claimed. No
  public request, hosted call, model download, data deletion, commit, push or deployment.

## 2026-10-26 — Final offline completion attempt

- Fixed `scripts/test_database.py` so explicit test files and node selectors are passed to
  pytest without also collecting the full `backend/tests` directory. Added three focused
  selection tests. The exact async persistence selector then ran alone and passed against
  a uniquely named disposable PostgreSQL database, which the runner removed. The
  persistence test itself uses `await AsyncSession.get()`; no production persistence code
  changed.
- Ran 24 deterministic tests covering the research graph, offline Wikipedia provenance,
  request budgets, strict exact-quote handling and repair, and runner selection. All 24
  passed. A real Qdrant/local-embedding retrieval check for the selected Juniper PDF ranked
  its page 1 `12 kWh` passage first and page 2 second.
- Per the acceptance gate, ran exactly one bounded offline Web workflow using cached local
  `qwen3:8b` and the genuine previously saved Wikipedia S1 excerpt through a no-network
  replay adapter. Public search and hosted providers were disabled. The run was persisted
  as a separate LOCAL session/run and did not overwrite prior records. It reached planning,
  evidence collection, and sufficiency assessment, then failed at the 180-second limit.
  The five Ollama requests took 11.60, 58.15, 54.52, 27.41, and 27.68 seconds; the last
  returned HTTP 500 without a retained detail body. Metrics record 5 model calls, 1,487
  input tokens, 949 output tokens, 55.066 seconds of model-reported inference (distinct
  from request duration), and 180.05 seconds total. No report, claims, citations, or completed
  verification were produced. Its source row retains S1's real title and URL; the replay
  hash is over the saved excerpt, not the source record's original full-article hash.
- Combined was not run because Web did not pass its gate. During the model run free memory
  reached 18% with Ollama using about 6.2 GiB; the model was safely unloaded afterward and
  free memory recovered to 66%. Disk showed 9.5 GiB free before inference. Public HTTP
  attempts, paid calls, downloads, and model retries of the full workflow: zero.
- No production workflow, retrieval, citation, or verification code changed. The previous
  Ollama 500 remains unexplained; do not claim Web/Combined acceptance. After this
  attempt, added safe Ollama HTTP error logging for schema stage, model, status, category,
  and duration only; response bodies are not logged. A regression test verified a simulated
  500 body is not exposed. Focused checks passed, then `bash scripts/check.sh` passed with
  181 backend tests, 38 frontend tests, lint, formatting, mypy, TypeScript, production
  build, and Compose validation. The earlier PostgreSQL/Qdrant suite (225 passed, 3 optional
  skips) and browser suite (5 passed) remain valid; those areas were not changed by the
  diagnostic logging update. Details are in `docs/LIVE_WEB_COMBINED_ACCEPTANCE.md` and the
  resumable checkpoint is `docs/FINAL_COMPLETION_STATUS.md`.

## 2026-10-27 — Independent deterministic Web and Combined completion checks

- Confirmed the existing `phase7-local-demo.pdf` stored file matches its database
  record and that the indexed page 1 passage contains the Juniper `12 kWh` fact.
  Added its exact 1,164-byte synthetic PDF to `backend/tests/fixtures/` so the
  isolated Combined regression can exercise the same source bytes without
  accessing or changing the development document store.
- Added an offline parameterized integration test for Web and Combined. It drives
  the real API, LangGraph stages, saved evidence sources, sufficiency checks,
  report creation, claim verification, and scratch PostgreSQL persistence.
  Web replays saved authentic Wikipedia S1 metadata and text without HTTP;
  Combined uploads/indexes the existing PDF bytes in isolated storage and checks
  both source types, correct page/citation provenance, supported claims, and
  persisted report/verification. The deterministic model is labelled `mock`.
- Added a frontend regression that renders a Combined-shaped saved result with a
  document page citation and the saved Wikipedia URL and keeps the explicit MOCK
  label. This is UI fixture coverage, not a browser-based local-model acceptance.
- Corrected resource accounting: LLM call caps are checked before reservations;
  failed/cancelled calls release stale token reservations while estimated cost
  remains conservatively reserved after a potentially billable attempt.
- Improved safe Ollama failure categories for connection failure, HTTP status,
  timeout, malformed JSON, schema mismatch, exact-quote mismatch, output
  truncation, and context overflow. Existing logs retain status, schema stage, configured model, safe
  category, and request duration, without retaining prompts, documents, contacts,
  or HTTP 5xx bodies. The historical 500 remains unexplained.
- Targeted checks: provider-contract and request-budget suites passed (41); Web
  and Combined database integration plus async persistence checks passed (3);
  Combined UI component check passed (1). Final `scripts/check.sh`: 185 backend
  tests passed, 50 database tests deselected, 39 frontend tests passed, and Ruff,
  formatting, strict mypy, TypeScript, ESLint, production build, and Compose
  validation passed. The isolated PostgreSQL/Qdrant suite passed 232 tests with
  3 opt-in cached-model tests skipped; all 5 Playwright tests passed in mock mode.
- Resource check: 11 GiB disk free, 70% system memory free, cached Qwen3 8B
  present (5.2 GB), PostgreSQL healthy, and Qdrant running. No model inference
  was run because the prior five-call Web attempt exhausted 180.05 seconds and
  no concrete repair to the unresolved HTTP 500 was established. No public
  request, hosted call, model download, data deletion, commit, push, or deploy.
- Evidence boundary: deterministic Web and Combined pass. Web real-Qwen remains
  failed at sufficiency; Combined real-Qwen is unrun because the shared local
  sufficiency/provider path is not yet stable. Live Web remains untested.

## 2026-10-27 — Portfolio and publication review

- Reframed the README around the local Documents research assistant and its
  LangGraph/RAG architecture. Web and Combined are clearly marked experimental,
  with real-model and fixture-based results separated.
- Simplified the demo to a 3–5 minute walkthrough of two completed saved local
  sessions: the cited 12 kWh answer and maintenance-cost abstention. The guide
  explicitly says these are saved results, not fresh inference. Confirmed both
  completed LOCAL `qwen3:8b` records and their PDF page provenance in the local
  database using read-only queries.
- Updated resume and interview materials, corrected the malformed improvement
  answer, added architecture/evaluation context, and documented source provenance.
- Reviewed startup/shutdown helpers: startup forces local Ollama, disables hosted
  providers, keeps public search off without the ignored private contact, and
  leaves PostgreSQL/Qdrant/Ollama running at shutdown. No private contact value
  was read or displayed.
- Reviewed the two README screenshots and citation sample; documented that the
  citation-mobile image is synthetic UI content. Removed machine-specific home
  paths and saved database record IDs from documentation.
- Replaced the copied historical Wikipedia text in backend quote-repair and offline
  workflow tests with original synthetic kilowatt-hour prose, explicitly labeled as
  synthetic and served from a reserved `.invalid` URL. Replaced the frontend mock
  source metadata and text as well. The historical acceptance report was left intact.
- Reviewed the screenshots. Excluded the old phase 0–4 captures and two Phase 8A
  baseline images from the GitHub allowlist because they show a personal display name,
  saved IDs, and/or a non-synthetic legal document and research history. The current
  Phase 8A screenshots are synthetic UI samples or the saved Juniper local result.
- GitHub review found no initial commit or remote; no files were staged. `.gitignore`
  excludes private configuration, contact, uploaded data, model caches, and runtime
  output. The current credential and home-path scan found none in non-ignored text
  candidates. Evaluation data is explicitly synthetic/provisional.
- Focused checks passed after the fixture replacement: exact-quote repair 1 test,
  synthetic Web/Combined persistence 2 tests, and frontend report rendering 8 tests.
  Changed Markdown references and formatting were checked. No public request, model
  inference, download, destructive change, commit, or push was made.
