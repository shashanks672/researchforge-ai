# Live Web and Documents + Web acceptance test

**Date:** 22 October 2026 (Asia/Kolkata)  
**Result:** Neither mode passed end-to-end acceptance. The Web run failed during
evidence-sufficiency assessment. The Combined run was cancelled when its request
budget overrun was discovered. No additional live run was made.

## Environment and safeguards

- ResearchForge API and Phase 8A UI were available at `127.0.0.1:8000` and
  `127.0.0.1:3000`; PostgreSQL was healthy and the API reported schema
  `0005_local_providers`.
- Both services reported `execution_mode=local`, model `qwen3:8b`, Wikipedia
  search enabled, and hosted calls disabled. The UI displayed `LOCAL · qwen3:8b`.
- The private Wikimedia contact existed in its ignored, permission-restricted
  local file and passed the existing safe validator. Its value is deliberately
  omitted from this report.
- The existing ready `phase7-local-demo.pdf` was selected by its document record
  (`[saved record ID omitted]`). No other document was selected or
  modified. The existing 16 sessions were retained; the two test sessions are
  additional records.
- Before inference, the machine had 13 GiB free disk and 56% system memory free.
  Ollama confirmed the cached model was not loaded. The run timeout was 120 s,
  Ollama timeout 90 s, and concurrency limit one.
- The temporary API settings allowed one planned search, zero follow-up searches,
  and zero provider retries. `max_sources=2`, however, was mistakenly relied on
  to limit article fetches while `max_tool_calls` remained 18. The consequences
  and corrective action are described below.

## Test 1 — Web

**Question:** “What is a kilowatt-hour, and what quantity does it measure?”  
**Session:** `[saved record ID omitted]`  
**Run:** `[saved record ID omitted]`  
**Status:** **FAILED** (`execution_mode=local`, `error_code=invalid_output`).

The local planner returned two subquestions, but the configured cap allowed only
one search query: `kilowatt-hour definition`. One Wikipedia search and two article
fetches completed. The saved genuine sources were:

- `S1`, _Kilowatt-hour_: <https://en.wikipedia.org/wiki/Kilowatt-hour>. The saved
  passage says it is a unit of energy and that one kilowatt-hour is the energy
  delivered by one kilowatt for one hour. It also gives the joule conversion.
- `S2`, _British thermal unit_:
  <https://en.wikipedia.org/wiki/British_thermal_unit>. The saved passage is
  mostly about BTUs; it mentions a kilowatt-hour conversion but is secondary to
  this question.

The source titles, URLs, excerpts, and content hashes were saved under this
session. `S1` directly supports the requested definition. The workflow then
failed at `assessing_sufficiency`: the saved error is `invalid_output`, and the
UI reports that structured output or citation IDs were invalid. The persisted
verification record is failed, there is no completed report, and there are no
claims or final citations to validate. The exact invalid model payload/field is
not available in the persisted run, so the narrower cause cannot be established
from this execution.

**Timing and local model:** 48.459 s persisted elapsed time (48.472 s between
saved start/end timestamps); two LLM calls were recorded. Recorded model
inference was 7.022 s, model load 6.364 s, and throughput 16.95 tokens/s. The
sufficiency call was the invalid-output failure. No paid model was used.

## Test 2 — Documents + Web

**Question:** “According to my selected Juniper battery document, what is its
rated capacity, and what does the unit kilowatt-hour mean?”  
**Session:** `[saved record ID omitted]`  
**Status:** **CANCELLED** after detecting excessive fetch attempts.

The session names only the synthetic document above. Local RAG saved one passage
as `S1`, from `phase7-local-demo.pdf`, page 2, with document ID
`[saved record ID omitted]`. Its passage says the installation took
place in March 2025 and that the demonstration record does not provide an annual
maintenance cost. This retrieved passage does **not** support the requested
12 kWh capacity. No valid web source was saved, so the Combined evidence set did
not establish both parts of the question. There is no completed report, no
sufficiency result, and no claim-verification result. The run was cancelled
before it could answer or abstain.

The persisted document passage is source `S1`, chunk
`[saved record ID omitted]`, page 2, with content hash
`1f40208a9ab99071aa1d15f68e841e5c4896072c64bb347fb06dd4b6659e3184`.

The planner returned two subquestions and the one allowed query was
`rated capacity Juniper battery`. The run recorded one Wikipedia search and five
article-fetch attempts before the workflow reached sufficiency assessment. The
workflow continued trying search hits after unsuccessful fetches because its
`max_sources` limit counts saved sources, while `max_tool_calls` was still 18.
The saved warning only says an unsafe, inaccessible, or unsupported source was
excluded; it does not preserve the individual HTTP response details.

**Timing and local model:** the saved timestamps span 38.521 s; the last metrics
snapshot records 15.260 s elapsed and 8.476 s model inference. One completed
planning call is recorded. Because cancellation occurred while the run was at
the sufficiency stage, no sufficiency output or final report is available.

## Request accounting and limit breach

| Run             | Search attempts | Article-fetch attempts | Total provider request attempts |
| --------------- | --------------: | ---------------------: | ------------------------------: |
| Web             |               1 |                      2 |                               3 |
| Documents + Web |               1 |                      5 |                               6 |
| **Total**       |           **2** |                  **7** |                           **9** |

The authorized limits were two searches, four article fetches, and six total
external HTTP requests. Search count stayed within its limit, but article fetches
exceeded the per-run Combined limit by three, the total article-fetch limit by
three, and the total request limit by three. This was an execution/configuration
failure. Once found, the Combined run was cancelled; no more public requests were
made. These counts come from the persisted provider-call metrics; exact server
receipt for each failed request is not separately logged.

The Wikipedia adapter disables redirects (`redirects=0`) and the run used
`provider_retries=0`, so no redirect target or automatic retry was followed.
Saved records contain no explicit 429/rate-limit error. The generic source
exclusion warning prevents determining the HTTP response for each failed fetch,
so this test cannot certify that every Wikimedia response was free of an access
or rate-limit error.

The prompt also limited fetched article text to 20,000 characters per article.
That bound was not configured or measured here: the current adapter downloads up
to 256,000 bytes and extracts the full page text before saving only a shorter
excerpt. The saved run does not retain full-text lengths. Compliance with the
20,000-character limit therefore cannot be established, and the next test must
enforce the limit before any new public request.

## UI, persistence, provenance, and validation

The composer exposed Web and Documents + Web while keeping My Documents
available. Starting each session in the UI created a persisted session and run;
history retained the earlier sessions. The report view showed the Web run as
“Could not finish” with its two retrieved web sources, and the Combined view
showed “Cancelled” with its one saved document passage. Both views identified
local Qwen inference. Neither run was labelled MOCK or LIVE. No mock source was
substituted.

Web source metadata and saved excerpts have matching session IDs and stable
source IDs (`S1`, `S2`). `S1` contains a passage relevant to the question; `S2`
is secondary. These are source records, not report citations: because the run
failed, no citation-to-claim relationship was created. The Combined document
source has the selected document ID, a chunk ID, filename, page 2, and saved
passage, but it does not support the requested capacity. The run has no persisted
web source. Citation validation and claim verification did not complete for
either test.

The Ollama model was stopped after testing to release memory. After unloading,
the system reported 64% free memory and no throttled pages; 12 GiB disk remained
free. There were no active research runs.

## Offline checks and next steps

The one-search configuration is now representable (`max_search_queries=1`); an
offline regression test verifies the single-search, zero-follow-up, zero-retry
configuration. Targeted `test_system.py` passed (12 tests), and Ruff lint and
format checks passed for the two changed Python files.

Before another explicitly approved live acceptance test:

1. Add a hard per-run article-fetch-attempt budget (failed fetches must consume
   it), or set `max_tool_calls=3` for a test configured with one search and at
   most two article fetches. Do not treat `max_sources` as an HTTP request cap.
2. Enforce and record the 20,000-character article-text cap in the adapter, with
   a focused offline test. Keep redirects and retries disabled for the bounded
   test.
3. Improve failure diagnostics so structured-output validation reports a safe
   stage/schema error and source fetch failures distinguish status classes
   without logging the private contact.
4. Investigate why Combined retrieval returned page 2 rather than the passage
   containing the stated rated capacity. Use offline retrieval evaluation first.
5. Use a separate approved live test; do not rerun either session or reuse these
   held-out live outcomes as tuning data. The two modes remain unaccepted until
   fresh runs complete with real evidence, a supported/qualified report,
   citations, and verified claims within strict request and text limits.

The earlier offline check record, before the remediation below, was: `bash
scripts/check.sh` passed Ruff lint/format, mypy, 167 backend tests, frontend
lint/format/type checks, 38 frontend tests, and the production Next.js build.
Forty-five backend tests were deselected by the script's `not database` marker;
database integration and browser automation tests had not been rerun at that
checkpoint. The actual Phase 8A UI was checked manually during both persisted
sessions. Those counts describe the earlier checkpoint only; updated offline
results follow below. No Wikimedia request was made by those checks.

## Offline remediation — 2026-10-22

This section records offline work after the breach above. The original request
counts and failed sessions remain unchanged. No public HTTP request, hosted model
request, paid call, or model download was made in this work. Reads against the
existing API, PostgreSQL and Qdrant were restricted to `127.0.0.1`; Wikipedia
content used in model probes came from the already-saved Web run.

### Request limits and failure persistence

Each research run now has one atomic request gate shared by its search adapter,
article fetches, redirects, retries, and follow-up research. The default limits
are one search request, two article-fetch attempts, and three total outbound
attempts per run. Every attempt reserves capacity before the GET starts, including
requests that later fail. Redirect targets reserve separately before they are
requested. External retry count is configured separately from local model
retries; `RF_MAX_EXTERNAL_RETRIES=0` keeps the acceptance setting at zero public
retries while allowing a bounded local structured-output repair attempt.

An optional `RF_MAX_GLOBAL_EXTERNAL_REQUESTS=6` shares a six-attempt ceiling
across runs handled by one API process. Its counter lasts for that process
lifetime, so an acceptance window must not restart the API between its two runs.
Per-run limits remain active if the process-wide cap is unset. Budget exhaustion
stops the workflow and persists `request_budget_exceeded`, a safe user-facing
message, and the request counters. Cancellation stops pending workflow work and
the final metrics snapshot is saved with the cancelled run.

Offline regressions cover two failed fetches followed by a blocked third fetch,
12 concurrent fetch attempts bounded at two, two runs sharing exactly six
attempts, an external retry count of zero while local retries remain enabled,
redirect rejection before the redirected GET, and a workflow that stops after
failed article fetches consume both slots. A PostgreSQL test confirms that a
budget error and its counters are persisted and visible. The tested request
sequence is at most `1 search + 2 fetches = 3 attempts per run`, then at most
`3 + 3 = 6 attempts across two runs`.

Article text is capped after extraction at 20,000 characters, independently of
the raw-response byte limit. Saved web source records now have a `text_truncated`
flag, and the run warning explains when truncation occurred. A fixture test
checks both the cap and flag.

### Structured-output failure

The saved Web evidence reproduces the failure. With only the saved `Kilowatt-hour`
passage, Qwen returned JSON that passed the sufficiency schema and said
`SUFFICIENT`, but its two supporting quote strings were each 206 characters and
neither was an exact or whitespace-normalized substring of the cited excerpt.
The server rejected the response with `supporting quote is not present in the
cited source`. That is the cause of `invalid_output`; the saved model output was
not itself retained by the earlier run.

The sufficiency prompt now explicitly forbids paraphrasing, changing symbols,
adding ellipses, or repairing odd source text. A single validation retry uses a
separate repair prompt that asks the model to re-evaluate and use `MISSING` if it
cannot copy an exact quote. The server still independently checks source IDs,
fact consistency, and exact quote substrings; no validation rule was relaxed.
Offline tests confirm that a near-match such as “3.6 megajoules” is rejected
when the excerpt only says “3.6 MJ”, and that the repair path is called only
after an invalid response.

Local inference was available: before testing, the machine showed 12 GiB free
disk and 73% free memory, and the cached `qwen3:8b` model was present. One direct
check using both saved Web sources passed schema and exact-quote validation. A
single-source check remained invalid, as described above. Full offline workflow
attempts reached planning, collection, and sufficiency but did not progress to
report writing or claim verification:

| Offline run | Last stage              | Outcome                                                  | LLM calls | Fixture request attempts | Model inference recorded |
| ----------- | ----------------------- | -------------------------------------------------------- | --------: | -----------------------: | -----------------------: |
| Web         | `assessing_sufficiency` | Failed `invalid_output`, including one same-prompt retry |         3 |                        2 |                  6.393 s |
| Combined    | `assessing_sufficiency` | Failed `invalid_output`, including one same-prompt retry |         4 |                        2 |                 27.737 s |

These full runs happened before the repair-specific retry path was connected in
the workflow. At this checkpoint the new path had only passed its offline
regression. A later isolated Ollama attempt is recorded below. The full Web and
Combined local-model checks remain incomplete. The failed attempts were
in-memory workflow executions; they did not create or alter research sessions.

### Focused quote-repair check — 2026-10-26

The saved failed Web session was read from local PostgreSQL in a read-only
transaction; no session or evidence row was changed. Its original question and
S1 excerpt were passed directly to the local `qwen3:8b` sufficiency method, with
search disabled. Before inference, disk had 8.9 GiB free and system memory was
74% free; the model was already cached. Five focused deterministic tests passed
before the model check, including a fixture where a paraphrased quote is rejected
and a single repair response succeeds only with an exact substring and known
source ID.

The bounded local check made two Ollama requests: one assessment and the one
allowed repair. The first response failed with `supporting quote is not present
in the cited source`. The repair response stopped at the test's `num_predict=512`
limit (`done_reason=length`) and the provider returned `budget_exceeded`; the
repair quote and completed JSON were not available to validate. Total elapsed
time was 92.041 seconds. The 512-token cap was set only for this focused test;
the normal configured output limit is 1,500 tokens. Thus the result confirms the
original quote failure, but does not establish whether repair succeeds at the
normal output limit. No other Ollama evaluation was run. No public request,
research workflow, new session, or saved-data mutation occurred.

The focused deterministic checks passed (4 provider-sufficiency tests, 1 repair
workflow test, and 3 answerability tests). The fixture and local check preserve
strict quote and citation validation; there is no server-side approximate quote
rewriter. At this checkpoint the full offline workflow was not justified. The
later normal-limit sufficiency result and subsequent workflow attempt are
recorded below.

### Combined retrieval

The existing local Juniper document was inspected read-only. With the previous
small-corpus BM25 ranking, a two-page query returned page 2 first (installation
date and missing maintenance cost) and the directly relevant page 1 passage
second (rated capacity `12 kWh`). BM25Okapi had negative IDF scores in this tiny
selected corpus, which made the weaker passage rank first.

Retrieval now uses BM25Plus, which keeps these small-corpus term contributions
positive. Combined mode requests a broader candidate set, ranks document
passages by the lexical score, and leaves one source slot for web evidence. The
workflow regression checks that a lower-ranked page 1 capacity passage is
retained alongside a real-provenance web source. A PostgreSQL/Qdrant regression
uploads a two-page test PDF and confirms the direct capacity passage ranks
first. Selected-document filters and all citation checks remain in place.

### Verification and remaining acceptance gap

Final offline checks passed:

- `bash scripts/check.sh`: Ruff, formatting, mypy, 176 backend tests, 38 frontend
  tests, and the production Next.js build.
- `backend/.venv/bin/python scripts/test_database.py`: 220 tests passed and
  three optional cached-embedding evaluations were skipped. This used a fresh
  disposable PostgreSQL database, temporary storage, and a unique Qdrant
  namespace; the harness removed those test resources.
- `backend/.venv/bin/python scripts/test_database.py --browser`: all five
  Playwright browser tests passed against local mock-mode services, including
  saved report and citation display. This verifies the existing UI’s persisted
  mock report path, not a Qwen-generated Web or Combined report.

There is still no successful local Qwen document-to-report execution to verify
PostgreSQL persistence, local-mode labeling, final citations, claim assessment,
or UI rendering for Web and Combined. The prompt repair has passed an isolated
Ollama sufficiency test, but no complete run has passed. A separate genuine live
Wikipedia acceptance test also remains outstanding.

## Offline workflow attempt — 2026-10-26

**Web: FAIL at evidence sufficiency. Combined: PARTIAL (not run).** This was an
offline-only attempt using the existing local Qwen model, saved Wikipedia S1/S2
records, and the saved `phase7-local-demo.pdf`. No public search, hosted model,
or external HTTP request was configured. The PDF file checksum matched its
existing document record, and the saved page 1 chunk contains the rated-capacity
statement `12 kWh` with its existing document, chunk, and page metadata.

The test used an isolated scratch PostgreSQL database for run/session
persistence. Ollama's loopback access log shows two requests: the planning call
returned HTTP 200 in 11.92 seconds; the next call returned HTTP 500 in 11.57
seconds. Given the workflow order, the second request was the evidence-sufficiency
call. No repair request was observed. The exact Ollama HTTP 500 detail was not
available, and the workflow's own stage, total elapsed time, token metrics, and
final persisted status were not captured.

The test harness then failed while reading the scratch session: it called async
`AsyncSession.get()` without awaiting it and raised `AttributeError: 'coroutine'
object has no attribute 'status'`. The scratch database was dropped in cleanup;
the original database, sessions, document, and file were not changed. Because
the run did not pass sufficiency and its final state was not recoverable, no
Combined run was started. No production code was changed.

No Qdrant service was started. The local image is cached, but the Web gate failed
before Combined could be attempted. The planned Combined path would have used a
deterministic retrieval fixture built from the checked local PDF and its
persisted chunk metadata; this would validate the LangGraph and persistence path,
but not Qdrant ranking. Web and Combined offline acceptance remain incomplete.
The scratch persistence inspector's async read was corrected and tested below.
Genuine live Wikipedia acceptance remains a separate, untested check.

## Ollama sufficiency diagnostic and persistence-inspector correction — 2026-10-26

**Prior HTTP 500 root cause: unknown.** Ollama's retained log contains the
loopback access entry with HTTP 500 and duration only; neither the response body
nor an error-detail line was retained. The application log has no matching
traceback. Runner startup completed normally and recorded 8.3 GiB free system
memory and 11.8 GiB free Metal memory before that run. No retained log shows an
out-of-memory condition. These facts do not establish why that specific Ollama
request returned 500.

The previous sufficiency request used the schema-constrained Ollama `/api/chat`
path: `qwen3:8b`, `num_ctx=8192`, `num_predict=1500`, temperature 0, thinking
disabled, non-streaming, and a 2,222-character JSON schema. For the two saved
sources, the user JSON was 4,233 characters; the application context guard
estimated 1,058 tokens plus the 1,500-token output limit, below the 8,192-token
context window. The guard passed. Ollama was configured to run its local llama
server on loopback with an 8,192 context. The retained HTTP 500 was therefore a
server response, not an application-side quote-validation failure. The code maps
HTTP 5xx responses to `provider_transient`; it does not retain the response body.

The scratch persistence test now reads `ResearchSession` using
`await db.get(...)` and checks the associated completed run and verification
record using an async SQLAlchemy session. The focused test passed alone
(`1 passed`); Ruff and formatting checks passed. An initial invocation through
`scripts/test_database.py` unexpectedly ran the full suite because that wrapper
always appends `backend/tests`: 215 passed, 7 Qdrant-dependent tests failed while
Qdrant was stopped, and 3 opt-in tests were skipped. Its disposable database and
temporary files were removed. The focused test was then run separately against
a fresh disposable database and passed.

One isolated local diagnostic then used saved Wikipedia source S1, disabled
search, `qwen3:8b`, and the 1,500-token output limit. Both HTTP responses returned
200; JSON and schema parsing succeeded on both. The initial assessment failed
only the exact-substring check (`supporting quote is not present in the cited
source`), so one repair was attempted. The repair returned `SUFFICIENT`, passed
strict source-ID and exact-quote validation, and was not truncated. It made two
model calls, using 2,628 input and 1,020 output tokens total; model inference
was 28.586 seconds and 28.729 seconds, with 75.072 seconds total elapsed.
Before the diagnostic, the cached model was present but not loaded; the machine
had 9.3 GiB free disk and 72% free memory (16 GiB total). Ollama loaded the
existing model successfully, with a measured load time of about 4.1 seconds on
the first call. No public request, paid provider, or model download occurred. No
production code changed; the confirmed test-harness defect was the missing
`await`.

The diagnostic confirms that local sufficiency and exact-quote repair currently
work for the saved single-source case, but it cannot recover the cause of the
earlier HTTP 500. One bounded full offline Web run is now justified; Combined
should run only if that Web run completes. Neither full workflow was started in
this diagnostic, and genuine live Wikipedia acceptance remains unverified.

## Final completion attempt — offline Web gate — 2026-10-26

**Web: FAIL / PARTIAL. Combined: NOT RUN / BLOCKED BY GATE.** The final
completion attempt performed one Web workflow with local `qwen3:8b`, the saved
authentic S1 _Kilowatt-hour_ passage, and all public search and hosted providers
disabled. A test-only in-memory replay adapter supplied the saved title, URL,
and excerpt; it made no public request. The run was persisted separately as a
new LOCAL session (`[saved record ID omitted]`) and run
(`[saved record ID omitted]`). Existing sessions and documents were
preserved.

The workflow passed planning and evidence collection, then stopped during
`assessing_sufficiency` at its 180-second run limit. Ollama's local access log
contains five `/api/chat` requests in the run window: HTTP 200 in 11.60,
58.15, 54.52, and 27.41 seconds, then HTTP 500 in 27.68 seconds. Their logged
request times sum to about 179.36 seconds. No response body or detailed server
error was retained, so the cause remains unknown. Persisted metrics record five
local model calls, 1,487 input tokens, 949 output tokens, and 55.066 seconds of
model-reported inference time (a different metric from HTTP request duration).
The total run reached 180.05 seconds. The
latest persisted stage before failure was sufficiency assessment; no validated
sufficiency result, report, claims, final citations, or completed verification
were produced. The run is therefore not an end-to-end pass.

The run persisted one `web` source with the genuine saved S1 title and Wikipedia
URL. Its replayed text was the previously saved excerpt, and the run's hash is
for that excerpt; it is not the original full-article content hash. Since report
writing did not occur, there is no citation-to-claim relationship or final
citation validation to report.

Immediately before inference, the cached model was available, disk had 9.5 GiB
free, and system memory showed 79% free. During inference, memory free fell to
18% while Ollama used about 6.2 GiB. The model was then unloaded safely;
reported free memory recovered to 66%. There were zero public HTTP attempts,
zero hosted calls, and zero model downloads. No product code changed for this
workflow attempt.

Combined was not attempted because the explicit acceptance gate requires Web
to pass first. An isolated, non-LLM retrieval check against the existing
selected document and Qdrant did return the actual `phase7-local-demo.pdf`
page 1 passage containing `12 kWh` first, followed by page 2. This checks
retrieval only; it does not count as a Combined workflow or answer acceptance.

The database test wrapper was also corrected so a supplied exact pytest node
selector no longer adds the full `backend/tests` directory. Three selector
tests passed, and the async persistence test passed alone in a disposable
PostgreSQL database. Focused deterministic workflow, request-budget, quote
validation/repair and selector checks passed (24 total). The previous unknown
Ollama HTTP 500 remains unresolved. Do not repeat this expensive Web run or
start Combined without new diagnostic evidence and an explicit decision to
spend the local inference budget. Genuine live Wikipedia acceptance remains
pending and unauthorized.

### Safe Ollama HTTP failure logging

After the bounded attempt, the Ollama adapter was updated to log only the
schema-stage name, configured local model identifier, HTTP status, safe provider
category, and request duration when the provider returns an HTTP error. It does
not read or log a 5xx response body. A regression test uses a simulated 500 body
containing private-looking source text and confirms the body is absent from the
log. The focused test, Ruff, and strict mypy passed; the full `scripts/check.sh`
passed afterward (181 backend tests, 38 frontend tests, lint, formatting, type
checks, build, and Compose validation). This makes a future failure more
diagnosable; it does not explain or repair the observed 500. The historical
response body is gone and no additional model request was made.

## Independent deterministic workflow acceptance — 2026-10-27

**Web: PASS (offline deterministic only). Combined: PASS (offline deterministic only).**
Neither result is a local-Qwen or live-Web acceptance pass.

The test harness ran each mode separately through the real FastAPI execution API,
LangGraph stages, verification, and a newly created disposable PostgreSQL
database. A fixed inference fixture supplied planning, sufficiency, report, and
claim decisions. The Web fixture replayed the previously saved _Kilowatt-hour_
Wikipedia title, URL, and excerpt and did not call public search. Combined used
the exact existing `phase7-local-demo.pdf` bytes as a test fixture: its checksum
was copied from the existing stored file, then it was uploaded and indexed only
inside the disposable test environment. The original document and index were
not modified.

Both cases passed the checkpoints for planning, collection, evidence assessment,
report writing, claim verification, and final persistence. Web stored the saved
Wikipedia passage as a `web` source. Combined additionally retrieved the Juniper
`12 kWh` sentence from PDF page 1 as a `document` source with document, chunk,
and page metadata. Its report cited the PDF for the capacity statement and the
Wikipedia source for the unit definition; claim-source IDs resolved to saved
sources, evidence sufficiency was `SUFFICIENT`, and the deterministic verifier
returned `SUPPORTED`. The API report and verification endpoints returned the
persisted records. Run labels were `mock`, accurately identifying fixture
inference; no result was labelled LOCAL. A focused UI test also rendered a
persisted Combined-shaped mock run, displayed both source types and the document
page, and confirmed its explicit MOCK label. This UI check used test data and is
not a browser execution of the database acceptance run.

The Web case made five fixture LLM operations and the Combined case made six;
each used one saved fixture search and one saved fixture fetch. The call counts
are deterministic fixture work, not Ollama inference. The fixture transport
recorded zero outbound HTTP attempts. The final Web and Combined cases passed in
0.77 seconds together with the focused async persistence check. The
report renderer correctly escapes Markdown punctuation, so assertions compare
the rendered escaped form while source excerpts and citation IDs are checked
against the unescaped persisted evidence.

### Targeted reliability corrections

The persisted 180-second Qwen run and existing workflow traces showed sequential
model requests and left its actual HTTP 500 response detail unavailable. Its
plan split one definition question into two related subquestions, so it likely
spent additional time on a second sufficiency evaluation; this is a workload
contributor, not a proven cause of the 500. No prompt or inference-budget tuning
was made from held-out outcomes and no additional Ollama request was made.

The inspected workflow has these request boundaries:

| Stage            | Model calls / work                                                                                                        | Evidence from this project                                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Planning         | 1 structured local-model request                                                                                          | The failed run's first Ollama call returned HTTP 200 in 11.60 s. Its planner split the linked definition question into two subquestions.                                                          |
| Collection       | No LLM call; bounded document retrieval or planned search/fetch                                                           | Offline acceptance replayed one saved Wikipedia result. The test fixture records one search and one fetch operation but zero outbound HTTP. Combined also retrieved the indexed PDF passage.      |
| Sufficiency      | One sequential model request per planned subquestion; one repair request when an eligible structured/quote failure occurs | The workflow was still at this stage when the five-call run stopped. Per-request stage labels were not saved in those historical logs, so the other four calls cannot be assigned more precisely. |
| Report writing   | 1 structured request if sufficiency allows a report                                                                       | Not reached in the failed real-Qwen attempt; exercised by deterministic fixtures in both modes.                                                                                                   |
| Claim extraction | 1 structured request when the report has checkable claims                                                                 | Not reached by the failed real-Qwen attempt; exercised by deterministic fixtures.                                                                                                                 |
| Claim assessment | 1 structured request when extracted claims exist                                                                          | Not reached by the failed real-Qwen attempt; exercised by deterministic fixtures. No-claim abstention paths can skip extraction and assessment.                                                   |
| Persistence      | Database checkpoints and final transaction; no LLM request                                                                | Deterministic tests verified final run, report, source and verification records in a disposable database.                                                                                         |

Optional verification follow-up can add collection, sufficiency, writing, and
verification work within configured iteration/call caps. The workflow is
sequential, not parallel. The inspected defaults are `qwen3:8b`, 8,192 context
tokens, at most 16,000 prompt characters, 1,500 output tokens, temperature 0,
thinking disabled, non-streaming responses, one configured provider retry, a
90-second Ollama request timeout, and a 120-second overall run deadline. The last full Web acceptance used a
180-second test override and still failed. Per-call timeouts are not derived
from the remaining global deadline, so the outer run deadline can cancel a
long-running request when little time remains; this does not explain the saved 500. A separate isolated sufficiency diagnostic recorded a 2,222-character
schema and 4,233-character JSON input, below its configured context limits,
and then passed after one exact-quote repair. This confirms that one such
request can fit; it does not establish why the full workflow received HTTP 500.

Focused changes now release token reservations when an LLM operation fails or
is cancelled, check the LLM call cap before reserving resources, and retain
estimated cost reservations conservatively after failed billable attempts. The
Ollama adapter now reports distinct safe error codes for connection failure,
HTTP failure, timeout, invalid JSON, schema mismatch, exact-quote mismatch,
output truncation, and context overflow. Its HTTP diagnostic log keeps the
status, stage, configured model, safe category, and duration without reading or
logging HTTP 5xx bodies.
Connection failure (`provider_connection_failed`) is distinct from a missing
model (`model_unavailable`); run deadline and user cancellation remain distinct
(`run_timeout` and cancelled/interrupted state).
Focused tests cover these classifications and reservation cleanup. These changes
improve observability and accounting; they do not repair or explain the specific
historical Ollama 500.

Machine check before the decision about another inference: 11 GiB free disk,
70% system memory free, cached `qwen3:8b` present (5.2 GB), PostgreSQL healthy,
and Qdrant running. No local inference was justified: the previous Web run used
five calls over 180.05 seconds, with request durations totaling about 179.36
seconds and memory free falling to 18%; no reproducible server-side 500 fix was
found. A second Web attempt is therefore not run, and Combined real-model
acceptance remains blocked on the shared sufficiency/provider stability issue.

Final offline regressions for this checkpoint: `scripts/check.sh` passed 185
backend tests (50 deselected), 39 frontend tests, Ruff, formatting, strict
mypy, TypeScript, lint, production build, and Compose validation. The isolated
PostgreSQL/Qdrant suite passed 232 tests with three opt-in cached-model tests
skipped. The browser suite passed all five tests in mock mode. No public search,
hosted API, model download, destructive data operation, commit, push, or deploy
occurred. Live Web acceptance remains untested and unauthorized.
