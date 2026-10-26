# Phase 6 — Evidence sufficiency and controlled provider readiness

Phase 6 inserts an evidence sufficiency stage between retrieval and report writing. For
each planned subquestion, a structured evaluator returns `SUFFICIENT`, `PARTIAL`,
`INSUFFICIENT` or `CONFLICTING`, with passage IDs, missing information, an explanation,
an evaluator version and a server-generated timestamp. The evaluator checks what the
passages say; retrieval ranking alone does not decide whether an answer is supported.

The hosted evaluator is given only the question and bounded, same-run evidence. Its strict
provider output schema omits server-owned timestamps and labels. The backend derives the
boolean `sufficient` value, checks every evidence ID against the current run, checks
status consistency, and fails the run if the output is malformed. Document-only mode
retrieves only the selected documents; it does not fall back to web search. Combined mode
keeps document and web source types distinct.

If every planned question is `INSUFFICIENT`, the graph creates a citation-free abstention
report and does not ask the report writer to invent an answer. `PARTIAL` and `CONFLICTING`
status, evidence IDs and missing details are passed to the writer; the report discloses
these statuses and existing claim verification can still trigger bounded follow-up. When
follow-up finds new sources, the graph reassesses sufficiency and rewrites while retaining
the original draft and history. If follow-up adds no source, it does not spend another
evaluation call. Statuses appear in the saved report, run limitations and the frontend's
Answerability status section. They are categorical evaluator results, not confidence
scores or a truth guarantee.

The deterministic mock evaluator always abstains: synthetic web fixtures and the mock
document writer are not semantic evidence evaluators. This preserves a useful offline
demonstration without presenting mock output as an answer. Empty retrieval still fails
clearly with no completed report. Provider/evaluator failures cannot be silently treated
as a successful research run.

## Held-out evaluation

`evaluation/datasets/answerability-v1.json` has 6 development questions and 12 held-out
questions across direct, paraphrase, partial, no-answer, missing entity, unsupported
number, multi-passage, conflicting, negation, topical similarity, misleading keyword and
incomplete-context categories. It is synthetic and unreviewed. Binary `answerable` means
at least some requested information is supported; `PARTIAL` and `CONFLICTING` count as
answerable for that binary metric but still require qualified answers. `INSUFFICIENT` is
the binary unanswerable label.

Reproduce the fast lexical baseline and review CSV:

```bash
backend/.venv/bin/python scripts/evaluate_answerability.py
```

The lexical Jaccard threshold is selected by answerable-class F1 on development rows only
and applied once to held-out rows. Its held-out false-answer rate was 0.50 (3/6), with
0.50 correct abstention and 0.167 incorrect abstention across 12 synthetic questions.
This deliberately weak baseline shows why topical overlap should not authorize an answer.

The local semantic/BM25/hybrid score study needs the already cached BGE model and running
local PostgreSQL/Qdrant. It uses scratch resources and does not call a report-writer or
hosted provider:

```bash
docker compose --profile infrastructure up -d --wait postgres qdrant
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k phase6_retrieval_threshold_study
```

The recorded thresholds are selected on the six development examples; metrics are
measured on the 12 held-out examples. In this run, semantic top-score thresholding had a
false-answer rate of 4/6, BM25 0/6, and hybrid 3/6. BM25's 0/6 came with 1/6 answerable
recall and five incorrect abstentions among six answerable examples. This is a clear
precision/recall tradeoff on a tiny synthetic set, not a useful production threshold.
Semantic and BM25 scores depend on the corpus and configuration; hybrid reciprocal-rank
fusion scores are ranking signals, never answer probabilities. Full score distributions,
gaps, per-category confusion counts, thresholds and raw rankings are saved in
`evaluation/results/phase-6-retrieval-thresholds.json`. Lexical output is in
`evaluation/results/phase-6-answerability.json`.

For human review, follow [the annotation guide](../evaluation/annotations/answerability-guidelines.md).
Start with the 12 held-out rows, hide expected labels during independent first-pass review,
record disagreement, and leave `review_status` as unreviewed until a person has actually
checked the passages. Do not report reviewer agreement until independent labels exist.

## Provider preflight and live safeguards

Hosted selection remains `openai` + `brave`, server-side keys, a supported model, and
`RF_LIVE_CALLS_APPROVED=true`. The approval defaults false. Live configuration also
requires operator-confirmed input-token, output-token and search-request unit prices in
`.env`; no prices are bundled or assumed. For example, after checking current provider
pricing yourself, set `RF_INPUT_USD_PER_MILLION`, `RF_OUTPUT_USD_PER_MILLION`, and
`RF_SEARCH_USD_PER_REQUEST` to those confirmed rates. ChatGPT subscriptions do not supply
OpenAI API credit.

Cost accounting reserves the configured search unit price before each paid search
request. Before an LLM request, the budget checks call/token limits and an estimated
maximum context/output cost; after a response it accounts for reported usage and checks
the run cap. Retries count as attempts. A timeout or cancellation cannot undo a request
already sent, and provider-side billing can differ from operator prices and estimates.
Keep `RF_MAX_ESTIMATED_COST_USD`, `RF_MAX_TOTAL_TOKENS`, `RF_MAX_LLM_CALLS`, search/tool
limits, and timeouts small for the first test.

Inspect the local configuration without contacting OpenAI, Brave or web sources:

```bash
backend/.venv/bin/python scripts/live_smoke_test.py --dry-run
```

This checks the loopback API's `/ready` and public configuration, server/local settings
match, credential presence (never values), approval, model, price configuration, cost
estimate and run limits. It exits blocked if any required setting is missing. The API's
public config exposes safe operational caps but no secret values.

Research runs emit structured JSON stage events with session/run IDs, stage, configured
provider pair and model, elapsed time, request/tool/token counters, estimated cost,
candidate count, sufficiency statuses and safe error codes. Question text, source passages,
credentials and raw exception details are excluded.

The future single-task execution form is:

```bash
backend/.venv/bin/python scripts/live_smoke_test.py --execute \
  --approve-live-spend --max-cost-usd 0.25 --wall-timeout-seconds 120
```

This command requires the CLI spend-approval flag, live server approval, a matching
loopback server configuration, current operator-supplied prices, and a worst-case token
and search estimate within the exact configured cap. It saves one `web` research session,
polls until terminal status, and requests cancellation on timeout. Its maximum request,
token, timeout and cost limits come from server configuration. Do not run `--execute`
until you have confirmed the provider prices, exact question, enabled live configuration
and cost ceiling and intentionally approved that run. Phase 6 did not run this command.

## Verification and regression commands

```bash
bash scripts/check.sh
backend/.venv/bin/python scripts/test_database.py
backend/.venv/bin/python scripts/test_database.py --browser
backend/.venv/bin/alembic -c backend/alembic.ini check
```

The offline check exercises mocked provider contracts and has no paid API tests. The
database test runner creates a scratch PostgreSQL database and isolated Qdrant namespace,
then removes them. The browser runner uses its own scratch services. The two existing
Phase 5 cached-model integration evaluations remain opt-in:

```bash
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k local_retrieval_evaluation
```

Phase 6 verification completed with `bash scripts/check.sh` passing (146 backend unit
tests, 34 frontend tests, lint/format/type checks, production build and Compose validation),
the isolated database suite passing 187 tests with 3 cached-model evaluations skipped by
default, and 5 browser integration tests passing. The opt-in Phase 6 BGE/Qdrant threshold
study passed separately. Alembic reported no new schema operations. No model was
downloaded; the cached local embedding model was reused. Memory use was not measured.

## Learning guide

1. **Evidence sufficiency** asks whether the retrieved passages actually contain enough
   information to answer the question. A passage about batteries may be relevant to a
   battery question but say nothing about its warranty.
2. **An unanswerable question** asks for a fact absent from the allowed sources, such as a
   warranty duration when the only passage states the battery capacity.
3. **Vector retrieval can return a result anyway** because it ranks similar wording or
   topics. A high rank says “nearby in embedding space,” not “contains the requested fact.”
4. **Abstention** is a system's explicit decision not to make an unsupported claim. The
   report says evidence is insufficient instead of guessing.
5. **False answer rate** is false positives divided by all labelled unanswerable questions.
   Three false answers among six unanswerable questions is `3/6 = 0.50`.
6. **A held-out set** is reserved for evaluation after threshold selection. It estimates
   performance on examples not used to choose the threshold.
7. **Data leakage** happens if the held-out labels influence the threshold or model choices.
   This benchmark uses development rows for threshold selection and applies it once to the
   held-out rows.
8. **LangGraph continuation and stopping** follow explicit edges: retrieve, assess, write,
   verify, and follow up only for important unresolved claims while iteration and call
   budgets remain. A new follow-up source triggers another sufficiency review.
9. **API keys** are secrets read by the backend from ignored local environment settings.
   They are not sent to the browser, included in prompts, or printed by the preflight.
10. **Token costs** depend on provider/model pricing and input/output token counts. Search
    may have its own price per request. Set prices only after checking current provider
    terms.
11. **Spend safeguards** combine explicit live approval, bounded calls/tokens/time, a
    configured cost ceiling, pre-call estimates and post-call usage accounting. Estimates
    cannot guarantee provider billing exactly.
12. **Offline evaluation** runs `scripts/evaluate_answerability.py`; the cached-model score
    study is the opt-in `phase6_retrieval_threshold_study` command above.
13. **Inspect results** in `evaluation/results/phase-6-answerability.json` and
    `phase-6-retrieval-thresholds.json`; inspect a saved run in the UI's Answerability
    status section or its exported Markdown.
14. **Dry run** with `scripts/live_smoke_test.py --dry-run`; it checks local readiness and
    live prerequisites but makes no provider request.
15. **Before real API testing**, you must confirm current provider pricing, configure both
    providers and server-side keys, set and verify a low per-run budget, choose the exact
    question, and intentionally run the command with `--approve-live-spend` and a matching
    `--max-cost-usd`. No such approval or live call occurred in this phase.

Study [the workflow](../backend/app/research/workflow.py), [sufficiency contracts](../backend/app/research/sufficiency.py),
[provider safeguards](../backend/app/research/providers.py), [budget](../backend/app/research/budget.py),
[evaluation metrics](../backend/app/research/answerability_evaluation.py),
[the smoke-test CLI](../scripts/live_smoke_test.py), and
[the review dataset](../evaluation/datasets/answerability-v1.json).

## Limits and pending work

This phase has no independent human review and no live provider outputs. The dataset is
small, synthetic and unreviewed; the sufficiency evaluator is a prompted hosted-model
procedure that is not independently quality-validated. The mock evaluator intentionally
abstains rather than pretending to measure semantic ability. Retrieval thresholds fail
to separate answerable from unanswerable cases reliably and must not be enabled as a sole
runtime decision. Public deployment, authentication redesign, Kubernetes, model training,
and Phase 7 are outside scope.
