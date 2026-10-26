# Evaluation artifacts

These small local evaluations are reproducible engineering checks, not evidence of
general research quality. Fixture and corpus labels are provisional; no independent
human review has occurred.

## Phase 3 and 4 regression baselines

`phase-3-results.json` records six generated English documents and one relevant document
per question. All three methods scored 1.0 at K=3 on this easy pilot; it does not show
that hybrid search improves over its components. Reproduce it only with the already
cached model:

```bash
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k local_retrieval_evaluation
```

`phase-4-results.json` is the original 12 manually labelled controlled fixtures. The
deterministic mock scored 1.0 with zero false support on those cases; this is a small
regression baseline, not a generalization benchmark or live model result.

## Phase 5 datasets and results

- `datasets/retrieval-v1.json`: 16 synthetic passages and 20 queries, including direct,
  paraphrased, keyword, multi-passage, distractor and no-answer cases. IDs are stable.
- `datasets/verification-v1.json`: six supplemental fixtures for incomplete/contextual,
  question, multi-passage and date-sensitive cases; the earlier Phase 4 file supplies 12
  additional classification cases.
- `evaluation/results/phase-5-retrieval.json`: semantic, BM25 and hybrid results plus
  configuration, per-query latency, no-answer handling and integrity counters.
- `evaluation/results/phase-5-eligibility.json`: 12 eligibility category fixtures.
- `evaluation/results/phase-5-verification.json`: the 12-case Phase 4 labels plus six
  Phase 5 incomplete/context/date/multi-passage regressions.
- `annotations/verification-guidelines.md`: provisional annotation rules for a future
  independently reviewed benchmark.

The new local benchmark uses the actual small FastEmbed model and local Qdrant for
semantic search, and the existing PostgreSQL-backed BM25 and reciprocal-rank hybrid
implementation. All methods use the same uploaded passages and paired query set. The
writer and verifier are not called in the retrieval benchmark. Each query asks for the
same top ten ranking; metrics are calculated at K=1, 3, 5, and 10.

Run the deterministic claim and eligibility evaluations:

```bash
backend/.venv/bin/python -m pytest -c backend/pyproject.toml backend/tests/test_verification.py -k 'phase5'
```

Run retrieval on the already cached local model and existing local services:

```bash
docker compose --profile infrastructure up -d --wait postgres qdrant
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k phase5_retrieval_benchmark
```

No model or dataset is downloaded by these commands. The runner builds a disposable
PostgreSQL database and Qdrant namespace and cleans them up. It writes results under
`evaluation/results/`; no development records are removed. Do not enable the benchmark
if the embedding weights are not already cached.

## Metric definitions and boundaries

Recall@K is relevant results retrieved divided by all relevant IDs. Precision@K is
relevant results in the first K divided by K. MRR is the mean reciprocal rank of
the first relevant passage. nDCG@K discounts relevant passages lower in the ranking and
normalizes against ideal ordering. We use binary relevance. Answerable queries with no
results have zero recall, precision and reciprocal rank. No-answer queries are excluded
from those metrics; the empty-result rate is reported separately. Missing relevant IDs
and unknown retrieved IDs are counted, then excluded from relevance scoring. Duplicate
results count only at the first rank. Median latency uses all queries; nearest-rank p95 is
reported with at least 20 samples.

Verification reports accuracy, per-class precision/recall/F1, macro F1, confusion matrix,
false-support rate and eligibility accuracy. False-support denominator is every expected
case whose label is not SUPPORTED. The fixture citation-support accuracy checks whether
the deterministic procedure's SUPPORT decision agrees with the labelled support cases;
it does not establish source truth.

Scores of 1.0 on the verification/eligibility fixtures only confirm those exact
regression cases. They do not measure semantic entailment or factual truth. No live
OpenAI/Brave call, NLI model, external corpus, human annotation review, statistical
significance test, or confidence calibration has been performed. The local retrieval set
is small and synthetic, so no broad method superiority claim is justified.

## Phase 6 answerability and threshold study

`datasets/answerability-v1.json` contains 6 development and 12 held-out synthetic,
unreviewed examples covering direct/paraphrase, partial, absent facts/entities, numerical
details, multi-passage support, contradictions, negation, topical similarity, misleading
keyword overlap and incomplete context. Each question has explicit supporting passage IDs,
required facts and missing facts. `annotations/answerability-review.csv` is generated for
human review; every row remains `unreviewed`. Follow
`annotations/answerability-guidelines.md` and do not report a human-reviewed result until
independent labels are completed.

`scripts/evaluate_answerability.py` selects a lexical Jaccard threshold on development
rows, evaluates it once on held-out rows, and writes confusion matrix, per-category
counts, false-answer and abstention rates to `results/phase-6-answerability.json`. The
12-item synthetic held-out lexical baseline has a 0.50 false-answer rate (3/6), 0.50
correct abstention rate, and 0.167 incorrect abstention rate. The score is a deliberately
weak lexical baseline, not an LLM result.

The opt-in `phase6_retrieval_threshold_study` integration evaluation indexes that dataset
in an isolated PostgreSQL database and Qdrant namespace with the already cached local BGE
model. It calibrates semantic, BM25 and hybrid top-score thresholds on the development
split and reports held-out score distributions, top-score gaps, confusion matrices and
per-category errors in `results/phase-6-retrieval-thresholds.json`. In the recorded run,
false-answer rates were 4/6 semantic, 0/6 BM25 and 3/6 hybrid. BM25's zero false answers
came with 1/6 answerable recall and five of six answerable cases incorrectly abstained.
This is not evidence for a production cutoff. Reciprocal rank fusion remains a ranking
signal, not a calibrated probability.

Reproduce both studies:

```bash
backend/.venv/bin/python scripts/evaluate_answerability.py
docker compose --profile infrastructure up -d --wait postgres qdrant
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k phase6_retrieval_threshold_study
```

See [the Phase 6 guide](../docs/PHASE_6.md) for data definitions, annotation steps,
provider preflight and metric denominators.


## Phase 7 local-model answerability

`datasets/phase-7-answerability-v2.json` is separate from Phase 6 and includes four
development cases plus six fresh final-test cases. The synthetic labels are provisional
and unreviewed. Neither Phase 6 held-out labels nor the Phase 7 v1 pilot final labels were
used for calibration. `scripts/evaluate_local_sufficiency.py` calls only loopback Ollama
and writes raw case outputs to `results/phase-7-ollama-answerability-v2.json`; it makes no
search or hosted provider calls. Use `--development-only` for calibration. The v2 final
set was run once after freezing the method: 5/6 valid decisions, zero false answers among
4 unanswerable examples, 3/4 correct abstentions, 2/2 answerable recall, 5/6 accuracy,
and 0.75 macro F1. One conflicting case failed consistency validation on both bounded
attempts. Four accepted quotes had valid source IDs and exact text present in their cited
passages; this does not prove entailment. Invalid response usage is not included in token
or inference totals. These tiny results are provisional software observations, not a
general model-quality claim. Do not use the final-test rows to tune this method. Review
the labels independently and create a new test set for future substantive changes. See the
[Phase 7 guide](../docs/PHASE_7.md).
