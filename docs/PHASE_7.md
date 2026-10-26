# Phase 7: local model, bounded public search, and answerability

Phase 7 adds an opt-in local Ollama provider to the existing research workflow. The
browser still talks to the same local API and database; no new service or cloud account is
required. `RF_LLM_PROVIDER=ollama` selects local mode and records runs as `local`, so the
UI, persisted run and metrics do not present them as mock or paid hosted runs. There is no
automatic fallback to mock when Ollama is unavailable.

## Local model setup

Ollama must already be installed and the configured model downloaded. This implementation
reuses `qwen3:8b` by default and does not download it at application startup. To confirm
the local Ollama service and model are available, run `ollama list` and
`curl http://127.0.0.1:11434/api/tags`. The model uses Ollama's schema-constrained,
non-streaming [`/api/chat` endpoint](https://docs.ollama.com/api/chat); the structured-output
contract follows Ollama's [JSON schema guidance](https://ollama.com/blog/structured-outputs). The configured address must be a loopback HTTP URL;
environment proxy variables are ignored. Limits include an 8K context, bounded output,
request timeout, run timeout, one active worker and the existing per-run call/token caps.
Qwen3 thinking mode is disabled for bounded structured tasks.
Local usage reports token counts, inference time, model load time when Ollama reports it,
and generated tokens per second. Local run cost is zero; this does not mean the computer
uses no electricity or has no hardware cost.

Example local backend command (leave the UI loopback-only):

```bash
RF_LLM_PROVIDER=ollama RF_SEARCH_PROVIDER=disabled \
RF_LIVE_CALLS_APPROVED=false RF_EMBEDDING_PROVIDER=local \
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend \
  --host 127.0.0.1 --port 8000 --no-access-log
```

Set `RF_OLLAMA_MODEL` only to a model already installed locally. Public search defaults
off.

### One-command macOS startup

From the project folder, run `bash scripts/start_local.sh`. This checks Docker Desktop,
starts only the project's PostgreSQL and Qdrant services from cached images (`--pull
never`), verifies the already-installed `qwen3:8b` model, applies forward database
migrations, and starts or reuses the loopback API/UI. The script forces the Ollama
provider and disables hosted calls. If no private Wikimedia contact is configured, it
leaves search disabled so Documents mode remains available. It does not install
dependencies or fetch models.

To enable the opt-in Wikipedia provider, run
`bash scripts/configure_wikipedia_contact.sh` and enter your real public contact in the
hidden prompt. You can enter a plain email (saved as `mailto:`), an existing `mailto:`
address, or an HTTPS contact page. The contact is stored in `.local/wikipedia-contact` with owner-only
permissions; `.local/` is ignored by Git. Wikimedia receives the contact in request
identification when a Web or Documents + Web run uses search. To apply it to an already
running API, run `bash scripts/restart_local_api.sh`. That helper verifies the API's
project path and local model mode, checks that no research graph run is active, then
gracefully restarts only FastAPI. It never runs a search itself. `bash scripts/stop_local.sh`
stops only API/UI processes recorded as started by the startup helpers; it leaves Docker
services and Ollama running. If a port belongs to an unverified process, the helpers stop
and leave that process alone. Full setup and beginner steps are in the README.

## Bounded public search

The no-key adapter uses English Wikipedia's API only. It is an encyclopedia search, not a
general-purpose index of the public web. It sends no more than five titles per query,
truncates queries to 200 characters, waits at least one second between requests, and
fetches only the Wikipedia article URLs it constructs. Page content uses the existing
public-IP-only bounded fetcher, without redirects, ambient proxy configuration or arbitrary
user-entered URLs. The workflow continues through the existing LangGraph evidence
sufficiency, report and claim-verification stages, preserving `web` source type, article
title, canonical URL, excerpt, content hash and originating query. Combined mode also
retains selected document ID, chunk ID and page metadata. A failed search does not switch to
mock data; search-query failures fail the run closed.

Activation requires all of the following in the backend environment:

```dotenv
RF_LLM_PROVIDER=ollama
RF_SEARCH_PROVIDER=wikipedia
RF_FREE_SEARCH_ENABLED=true
```

The contact value belongs to the operator and must be a real HTTPS contact page or
`mailto:` address. Do not copy a sample identity or use a placeholder. It is sent in the
Wikipedia API `User-Agent`; this project cannot verify that the contact belongs to or is
reachable by the operator. Configuration now rejects malformed HTTP URLs, URL credentials,
malformed mailboxes and control characters before they can reach the request header. This
is syntax checking only; it cannot prove contact ownership. Planned search terms leave the
Mac and are sent to Wikimedia, so do not use public-search modes for confidential questions.
Selected document passages are retrieved locally and are not uploaded by the Wikipedia
adapter. The adapter is subject to Wikimedia's usage and User-Agent
policies and any rate limiting; it must not be used to evade CAPTCHA, paywalls or throttling.
No API key or subscription is required, but availability and request throughput are not
guaranteed. The public system endpoint reports the provider and enable flag without
exposing the contact value.

Article text is generally available under [CC BY-SA](https://en.wikipedia.org/wiki/Wikipedia:Copyrights),
subject to the applicable page history and any exceptions. Preserve source title and link
attribution when reusing text and follow share-alike terms for adaptations; non-text media
can have separate licenses. The app extracts article text and displays the title and source
link, but does not store per-source license metadata. Check the applicable license before
redistributing generated material.

This adapter is wired for `ollama/wikipedia`, and Web/Combined modes use the real adapter
and existing evidence graph when explicitly enabled. Offline tests now exercise search,
article extraction and source provenance with a mocked HTTP transport, so they make no
public requests. No external search request has been made. Therefore, public end-to-end
behavior remains unverified until the operator privately supplies their real contact
configuration and separately approves a bounded live test. The UI explains the adapter
scope and prerequisites while leaving Web and Combined unavailable when search is
disabled.

## Fact-level evidence checks

The model must break each question into requested facts and label each one supported,
missing or conflicting. A supported/conflicting fact must include an exact quote and a
source ID. The server checks that IDs exist, quoted wording occurs in that source's
excerpt, and the set of quote source IDs matches the decision's evidence IDs. Conflicts
need quotations from at least two sources. A `SUFFICIENT` decision requires all assessed
facts to be supported; a `PARTIAL` decision must contain supported and missing facts; an
`INSUFFICIENT` decision must identify missing information. Invalid output gets one
bounded retry and then fails closed. These rules catch missing or fabricated citations;
they cannot guarantee that a model has interpreted a real quotation correctly.

## Development and final evaluation

`evaluation/datasets/phase-7-answerability-v2.json` is new synthetic data, separate from
Phase 6. It contains four development cases and six fresh final-test cases. Labels are
provisional and not independently reviewed. Neither Phase 6 held-out labels nor the Phase
7 v1 pilot final labels were used for calibration. The development split informed one
prompt clarification about grouping incompatible values into one conflict assessment.
The method was then frozen and the v2 final split was run once. The runner saves raw
predictions and summaries to `evaluation/results/phase-7-ollama-answerability-v2.json`:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/evaluate_local_sufficiency.py
```

Use `--development-only` when calibrating; the final split remains untouched in that
mode. This runner talks only to loopback Ollama. It has no search tool and does not load
provider secrets. Do not alter thresholds or prompts based on these six final-test rows
and then report that same set as an independent test. To test a changed method, author a
new fresh test set. A human review should check question wording, evidence completeness,
fact decomposition, and expected status before any score is treated as more than a
software regression.

The frozen v2 run recorded 5 valid decisions out of 6 (83.3% structured-output and
consistency validity), 0 false answers among 4 unanswerable cases, 3 correct abstentions
out of those 4 (75%), 2/2 answerable recall, 5/6 accuracy, and 0.75 macro F1. One
conflicting-evidence case was rejected on both bounded attempts because the overall status
did not match its fact-level statuses. The runner fails this case closed; it does not
count the error as a correct abstention. All 4 evidence quotes in accepted outputs had
valid source IDs and exact text present in their cited passages. Exact quote validation
does not establish that a quote logically supports the requested fact. Since invalid
responses do not return usage metadata through the provider contract, token and inference
totals omit those failed attempts; their wall-clock time is still recorded. Treat all
these numbers as small provisional engineering observations, not a general quality claim.

## Verified local Documents-mode demonstration

On 2026-10-19, the full Documents-mode workflow was run with the already cached `qwen3:8b`
through the local UI and API. PostgreSQL and Qdrant used their existing Compose volumes.
A two-page synthetic PDF was uploaded and indexed with the already cached local BGE
embedding model. The answerable question was “What is the rated capacity of the Juniper
battery?” The final report cited the retrieved passage on page 1, including its exact
wording, and claim verification marked the factual claims supported. The stored session
and run have `execution_mode=local`; the UI displayed `LOCAL MODEL · qwen3:8b`. This is one
successful local document-to-report execution, not a broad quality guarantee. The cited
passage was document `[saved record ID omitted]`, chunk
`[saved record ID omitted]`, page 1; the quote was “The Juniper battery has a
rated capacity of 12 kWh.”

The successful answerable run used five Qwen calls: planning, evidence sufficiency, report
writing, claim extraction, and claim assessment. It retrieved two document passages; made
zero search, fetch or other tool calls; and reported zero estimated cost. It took 89.142
seconds end to end, with 60.888 seconds of reported inference, 1.074 seconds of reported
model load, and 4,089 input / 1,121 output tokens. Cumulative stage logs imply approximate
times of 14.9 s planning, 0.1 s retrieval, 15.4 s sufficiency, 23.6 s report writing and
35.1 s claim extraction plus assessment. The stage-time breakdown is approximate because
the workflow stores cumulative timestamps rather than individual stage durations.

The deliberately unanswerable question was “What is the Juniper battery annual maintenance
cost?” Qwen planned the question and assessed evidence, returning `INSUFFICIENT`; neither
retrieved passage contains that cost. The workflow completed with an explicit insufficient-
evidence report and zero claims, with no invented price. It used two Qwen calls, took
25.739 seconds and reported 1,444 input / 307 output tokens. Report generation used the
deterministic abstention template; claim extraction and verification were correctly
skipped because there was no factual answer to check. It made no search or fetch calls.

During integration, one early answerable attempt failed at evidence sufficiency with
`invalid_output` after the planner expanded a single requested fact into three subquestions.
After the planner prompt was narrowed, the model returned an internally inconsistent
aggregate sufficiency status despite correctly identifying the supported fact and quoting
its passage. The provider adapters now derive redundant aggregate status from fact-level
decisions before normal validation; exact quote, source ID, and conflict checks remain
enforced. The planner now keeps a single factual question to one subquestion. A
separate unanswerable run initially sent the boilerplate abstention through claim extraction
and failed verification; document-only all-insufficient runs now skip that unnecessary
model step. A repeat answerable attempt did fail at verification (`verification_failed`),
showing small-model variability. The completed answerable and unanswerable runs above
demonstrate successful executions, but this single-pair result does not imply repeatability.

The report renderer now labels uploaded evidence as “document passage” rather than the
previous generic “web source”; the corresponding persisted-document regression test checks
that label and the real page/chunk citation metadata. The earlier successful answerable
run's saved report was produced before this display-label correction, so its source metadata
and page citation were correct but its rendered parenthetical label was stale. The
unanswerable report generated after the fix displayed the correct document label in the UI.

Resource observations: the cached model occupied about 5.2 GB; system free memory was
78–81% before inference, fell to 25–26% while the model held about 6.2–6.5 GB, and recovered
to 64–70% after `ollama stop qwen3:8b`. Disk space was 11–12 GB free before and after the
runs. The inference completed safely. Ollama, embeddings, PostgreSQL and Qdrant were local;
search was explicitly disabled and no public, hosted or paid request or model download was
made. Existing documents and sessions were preserved. One temporary synthetic document
and demonstration sessions were added.

The manually inspected UI and persisted run both identified the completed run as LOCAL.
The model-backed answerable run exercised planning, sufficiency, report writing, claim
extraction and verification. The no-answer run intentionally did not invoke report-writing
or verification models. Public search was not tested, and the optional automated
real-model browser test was not run; neither is needed to establish the successful local
Documents-to-report execution described here.

### Reproduce on the same Mac

These commands reuse installed tools, local model files and existing database/vector-store
volumes. `ollama list` is a check only; do not run `ollama pull` for this demonstration.
Keep the UI and API bound to loopback:

```bash
cd /path/to/researchforge-ai
ollama list                         # confirm qwen3:8b is already present
curl -fsS http://127.0.0.1:11434/api/tags  # confirm the local Ollama service responds
docker compose --profile infrastructure up -d --wait postgres qdrant
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
```

If the Ollama API check cannot connect, open the installed Ollama app or run `ollama serve`
in a separate terminal. Do not use `ollama pull`.

In a terminal, start the local API with search and paid calls disabled:

```bash
cd /path/to/researchforge-ai
RF_LLM_PROVIDER=ollama \
RF_OLLAMA_URL=http://127.0.0.1:11434 \
RF_SEARCH_PROVIDER=disabled \
RF_FREE_SEARCH_ENABLED=false \
RF_LIVE_CALLS_APPROVED=false \
RF_EMBEDDING_PROVIDER=local \
RF_RUN_TIMEOUT_SECONDS=180 \
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend \
  --host 127.0.0.1 --port 8000 --no-access-log
```

Start the frontend with `cd frontend && npm run dev` if it is not already running, then
open `http://127.0.0.1:3000`. Check the public configuration with
`curl http://127.0.0.1:8000/api/v1/config`; it should show `execution_mode: local`,
`llm_provider: ollama`, `model: qwen3:8b`, disabled search and `live_calls_approved: false`.
Upload the existing synthetic file
`/tmp/researchforge-phase7-local-demo.pdf` (or recreate a two-page file with the same
passages), wait for indexing, and start a **Documents**-mode session selecting that file.
Run each question separately:

1. `What is the rated capacity of the Juniper battery?` Expected: `12 kWh`, page 1 citation.
2. `What is the Juniper battery annual maintenance cost?` Expected: an insufficient-evidence
   report and no cost value.

Check the run says LOCAL in the UI and persisted `execution_mode`, and inspect each source's
document ID, chunk ID, page and quoted passage. `ollama stop qwen3:8b` releases model memory
afterward; stop the local API with Ctrl+C and, if desired, stop only these local services
with `docker compose --profile infrastructure stop postgres qdrant`.

No model download or runtime installation occurred during this validation.

To check the existing model, run `ollama list`. If the Ollama macOS app is already open,
the service is normally running; otherwise start it with `ollama serve` in a terminal and
stop that manually started service with Ctrl+C. Do not run `ollama pull` unless you
separately decide to download a model and have checked available disk space.

## Result boundaries

The small evaluation can reveal structured-output failures, false answers and missed
answers on these exact cases. It does not establish broad research quality, calibrated
confidence, or truth. Report the false-answer count over PARTIAL, INSUFFICIENT and
CONFLICTING cases, along with answerable recall, all four class counts, and raw case
predictions. If a model response fails validation, count it as an error rather than
quietly treating it as an abstention. Human review and a larger independent dataset remain
necessary before using results to choose an abstention threshold.
