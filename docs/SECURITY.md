# Local-only boundary and security roadmap

Phase 2 has no authentication and must stay on localhost. Both application start commands
bind to `127.0.0.1`. Compose database ports also bind there. Do not expose ports through
a tunnel, change binding to `0.0.0.0`, or deploy publicly at this stage.

Current safeguards: exact local CORS origins, host-header validation, strict typed input
contracts, fixed outbound health paths, local-only backend URL, redirects disabled for
that fetch, timeouts, explicit public configuration allowlists, sanitized proxy errors,
no secrets in browser bundles, no query/header/body logging by application middleware,
and ignored `.env`, storage and dependency directories. Uvicorn commands disable access
logs so future URL parameters do not accidentally get logged. The research tool surface
is restricted to bounded search queries and public page fetching; there is no shell/code tool.

Session writes additionally require JSON and reject untrusted browser origins. The Next.js
proxy validates the actual local Host against the browser Origin (Next.js may normalize
its internal URL), rejects cross-site Fetch Metadata, caps streamed JSON at 20,000 bytes,
validates fixed paths/query values and allowlists response fields. The API rejects
client-supplied status/workspace IDs, bounds questions and pagination, uses parameterized
SQL and filters all reads to the server's local workspace. Browser responses contain no
database URL. SQLAlchemy hides bound parameters; database exceptions are sanitized rather
than logged with SQL, questions or credentials. Database URL representations are redacted.

This is not write idempotency: when a response is lost after commit, inspect history before
retrying. Test runners create only fresh `rf_test_*` databases and clean up only those
databases; tests never reset development tables. The local development role has CREATEDB
for this purpose and is not a suitable production application role.

CORS is a browser read policy, not authentication. Host checks do not authenticate users.
Local processes and people with access to the machine can access this application.
Database development passwords are unsuitable for deployment. Qdrant is unauthenticated
in this optional local-only setup. These are explicit limits, not production controls.

Phase 3 implements extension/signature/content checks, upload byte limits, UUID storage
names outside the served frontend tree, path traversal prevention, parser time limits,
workspace filters and duplicate handling. Never use a supplied filename as a storage path.
The parser subprocess is not a complete OS security sandbox; only trusted local files
should be processed until stronger isolation and scanning are added.

Web extraction now uses a separate `SecureHTTP` path. HTTP(S) URLs have no credentials,
control characters, zone IDs or non-default ports. Literal private/reserved IPs are rejected.
Its aiohttp resolver checks every address used by the actual connection, rejects mixed
public/private answers (including mapped IPv4), and returns only validated numeric addresses
for connection while preserving host/SNI certificate checks. DNS caching, environment
proxies and ambient cookies are disabled. Redirects are manual/bounded and revalidated;
HTTPS downgrades are rejected. Authenticated search calls never follow redirects.
Decompression is disabled and nonidentity encoded responses are excluded to avoid bombs.
Streamed bytes, MIME types, provider deadlines and retries are bounded. Access failures
are excluded rather than bypassed. Tests mock DNS/HTTP; no internal service was probed.
Deployment still needs network-level egress restrictions. The local health proxy is not
reused as a web extractor. OpenAI uses a fixed trusted API endpoint and TLS through its SDK.

Hosted providers remain off without complete matching configuration, current operator-set
unit prices, and an explicit live-approval flag. Model names are restricted to supported capabilities. Planning has one
allowlisted strict function; report writing has no tools. Both are validated after response.
Secrets are not included in prompts, public config, run snapshots or errors. Configuration
validation hides raw input values. LangSmith tracing and its test plugin are disabled.

Worker ownership uses a PostgreSQL advisory lock; duplicate acceptance uses a pending-state
row lock and unique run/session constraint. Completion rechecks status in the transaction,
so a cancellation or failed mandatory stage cannot become completed. Stale runs fail safely
on ownership recovery and are not replayed. A lost database connection may delay persistence;
the app does not claim in-memory work is durable. Provider close/shutdown waits are bounded.

Treat retrieved webpages and documents as untrusted evidence. Keep them outside system
instructions. Providers receive only allowlisted research tools with bounded arguments,
never shell or filesystem execution. Validate model output and citation IDs. Escape
report HTML and sanitize Markdown links before rendering. Prompt defenses need tests
but cannot guarantee an LLM will ignore every malicious instruction.

Before any multi-user/public deployment, add authentication, workspace authorization on
every run/document/vector query, CSRF protection where cookies are used, deployment CORS,
rate limits, secrets management, encrypted transport, resource accounting and migrations.
Test cross-workspace access, malicious documents, rebinding, redirects, timeouts, download
limits, provider failures and cancellation. Security tests are expanded with each feature.

## Phase 3 document boundary

Uploads use bounded raw binary streaming with fixed API paths, local origin validation,
UUID storage names, extension/signature/parser validation and exclusive atomic storage.
Private keys/paths are absent from public metadata. Parser CPU/wall/expansion limits and a
separate process reduce exposure but are not a hostile-file sandbox or guaranteed macOS
memory limit. Only trusted local files until OS isolation/scanning is added. DOCX links,
macros and embedded files are not executed. PDF extraction does not perform OCR.

PostgreSQL ownership/readiness/generation are authoritative; Qdrant payloads filter local
workspace and selected document IDs and results are intersected with authorized chunks.
Model changes use separate collections; stale embeddings require reindexing. Failed jobs
cannot become ready. Deletion is explicit, retryable and blocked during document research.
Past run snapshots retain document excerpts after raw-file deletion; no full erasure claim.
Model downloads occur only in the explicit script; application startup uses pinned cached
weights. The selected English quantized model runs on CPU with two threads, no CUDA.

## Phase 4 claim assessment

Claims and retrieved passages are passed as untrusted data to the assessment model. The
model has no tools. Strict structured outputs are validated, every report location must
be covered, claim text and citation IDs must match the report, evidence quotes must be
exact substrings of same-run passages, and source IDs must exist in the current session.
A `SUPPORTED` verdict also requires a checkable claim, an existing draft citation, at
least one support passage, and no conflicting passage. Invalid mandatory output fails the
run; it cannot create a completed assessment. Document passage references are rechecked
against the current PostgreSQL document/chunk generation at final commit, so deleted,
reindexed or cross-workspace evidence cannot pass.

The lexical candidate ranker selects evidence for review but does not decide support.
Retrieved prompt-injection strings are excluded by the deterministic mock policy and
described as untrusted input in hosted prompts. Tests cover injection fixtures, citation
existence without support, fabricated quotes, unknown IDs, omitted claims, conflicting
passages and session boundaries. These defenses reduce risk but cannot guarantee a hosted
model will follow every instruction. An assessment is a bounded evidence-support
procedure, not a truth certification or calibrated confidence score.

Verification snapshots, original drafts, revised drafts and assessment history are
scoped to the local workspace. A failure or restart marks the assessment failed; a partial
snapshot is never promoted to completed. Follow-up research is limited by iteration,
tool, token, cost-estimate and wall-clock budgets. Cancellation cannot undo an already
sent provider request or its possible charge. No real hosted verification call has been
made, and the app remains unauthenticated and local-only.

## Phase 5 claim and evaluation boundaries

Extracted report text is checked by a deterministic eligibility gate before a verdict can
be considered. Fragments, questions, instructions, subjective text, and leading pronouns
without an explicit antecedent are kept in the audit record with a reason and forced to
NOT_EVALUATED. The original report text is preserved. The gate is a conservative English
heuristic, not a parser or a guarantee that every factual statement is recognized.

Claim and source content remain untrusted data. The assessment model receives structured
fields, has no tools, and cannot change source provenance. Retrieval evaluation labels are
stored in a separate synthetic dataset and are never used at runtime for retrieval or
verification. Current Phase 5 labels are provisional and not independently human-reviewed.
The deterministic fixture score is a regression result, not a security or factuality
claim. See [Phase 5](PHASE_5.md) and the
[annotation guidelines](../evaluation/annotations/verification-guidelines.md).

## Phase 6 sufficiency and provider controls

The sufficiency evaluator receives bounded same-run excerpts as untrusted input and no
tools. Its provider schema contains only the question ID, categorical status, evidence IDs,
missing details and explanation; the server supplies the timestamp/version and validates
that returned IDs exist. Unknown evidence, inconsistent status/boolean values, or missing
information for an insufficient result fail the run. Mock sufficiency always abstains.
Documents mode never falls back to web sources. Combined reports preserve document/web
source types and provenance. The report includes sufficiency statuses and citation-free
abstention if all planned questions remain unsupported.

Live mode now requires current operator-supplied LLM input/output token rates and search
request price. Search cost is reserved before an outbound paid query; LLM requests are
bounded by per-run calls, total tokens, context size, timeout and projected cost. Actual
reported token usage updates the estimate after each call. Rates and provider billing can
differ, and cancellation cannot undo a request already sent. The local preflight command
contacts only the configured loopback API's `/ready` and safe public configuration
endpoints. Its `--execute` mode is a separately approved one-task CLI path; it was not run
during Phase 6. Keep the existing app loopback-only; the CLI rejects non-loopback targets.
See [Phase 6](PHASE_6.md) for exact controls and pending human/live review.

## Phase 7 local inference and public search

The Ollama endpoint must be loopback HTTP; the local adapter ignores ambient proxy
settings, follows no redirects, bounds request and response sizes, and uses capped context,
output, retries and timeouts. Ollama is not exposed by the application. Retrieved text is
untrusted input. The server checks evidence IDs and exact quote substrings, but a local
model can still misunderstand what a quote means. Invalid sufficiency output fails closed.
Public Wikipedia search is disabled unless both an explicit enable flag and a real contact
address are configured. Phase 7 evaluation used only loopback Ollama. The user skipped the
public search test, and no external request was made. Keep the app local and unauthenticated;
these controls do not make it safe for public deployment.
