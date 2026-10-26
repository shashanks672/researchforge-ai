# ResearchForge AI — Interview Preparation

Use this guide to describe the code and the evidence actually available. Be direct about
the incomplete Web and Combined acceptance; a careful account of a failure is stronger than
claiming an unverified success.

## A short project explanation

“ResearchForge AI is a local-first research workspace built with Next.js, FastAPI,
PostgreSQL, Qdrant, LangGraph, and Ollama. It retrieves document passages, checks whether
they answer each requested fact, writes a cited report or abstains, then extracts and
assesses report claims. I focused on source provenance, bounded execution, and honest
failure handling. The local Documents workflow has completed an answerable and an
unanswerable demonstration. Full Web and Combined completion with local Qwen is still
unverified because a bounded Web run hit an Ollama HTTP 500 during sufficiency.”

## Likely technical questions

### 1. Why use retrieval-augmented generation?

The model needs task evidence from the user's selected documents instead of relying on
pretraining alone. Retrieval supplies bounded passages with document and page metadata.
The model receives those passages for sufficiency and writing. Retrieval can still miss
relevant passages, and the model can still misread them.

### 2. How does hybrid retrieval work, and what does Qdrant store?

The document service filters authorized, ready chunks, ranks them lexically with BM25Plus,
and searches Qdrant's vector collection using cached local embeddings. Qdrant stores vectors
for document chunks; PostgreSQL remains authoritative for document readiness and chunk
metadata. Reciprocal-rank fusion combines keyword and vector result ranks. This helps with
exact terms and semantic similarity, but it does not prove that a top result answers the
question.

### 3. Why LangGraph?

The workflow has distinct planning, collection, sufficiency, writing, extraction, and
verification stages with bounded branching. Explicit state and checkpoint callbacks make
progress and failure stages persistable. The app still uses one local worker and does not
provide durable graph resume after process restart.

### 4. What does evidence sufficiency validate?

It checks each planned question against retrieved facts and source passages. Each supported
fact must identify known source IDs and provide an exact quote substring; missing or
conflicting facts affect the overall status. A bounded repair may ask the model to re-evaluate
invalid output. This verifies schema and reference consistency, not semantic truth.

### 5. How are citations kept grounded?

Sources receive stable IDs within a run. Report statements can cite only those IDs. The
server rejects unknown IDs and invalid exact quotations. Document evidence also carries a
document ID, chunk ID, checksum, and page. Finalization checks that a cited document chunk
is still ready and from the current generation.

### 6. What is the difference between quote checking and claim verification?

Quote checking confirms a quote is present in the supplied passage. Claim verification
extracts report claims, selects candidate passages, and assesses support or contradiction.
Neither step establishes that the source itself is accurate or that model interpretation is
always correct.

### 7. How do you limit unsafe or expensive research?

The workflow has separate limits for local model calls, tokens, run time, search attempts,
fetch attempts, total external requests, retries, sources, and follow-up. External request
capacity is reserved at the HTTP boundary before an attempt; failed requests consume it.
Local structured-output repair does not create another public search attempt.

### 8. Why Ollama, and what does “local-first” mean?

Documents mode uses local storage, PostgreSQL, Qdrant, embeddings, and loopback Ollama. If
optional Wikipedia search is enabled, planned search terms and source requests go to
Wikimedia. Hosted model providers exist behind explicit configuration but were not used in
these local demonstrations. I would not send confidential questions to Web mode.

### 9. What evaluation evidence do you have?

There are deterministic unit, integration, and browser tests; one successful local
answerable document report; one local insufficient-evidence result; and a separate failed
answerable verification attempt. Deterministic Web and Combined flows now pass through the
real workflow and persistence using saved evidence and fixture inference. A small synthetic
answerability benchmark is provisional and not human-reviewed. The earlier deterministic
offline Web/Combined acceptance used saved Wikipedia evidence; the current bundled
regressions use original synthetic web text and fixture inference. A bounded offline Web
run with real local Qwen failed at sufficiency after an Ollama 500; Combined real-model and
live acceptance remain unverified. I report each evidence class separately.

### 10. What happened in the recent Web failure?

The graph planned, loaded saved Wikipedia S1 evidence through a local replay adapter, and
entered sufficiency assessment. The run reached its 180-second bound and Ollama's local log
recorded a 500 response. The response detail was not retained, so the exact server-side
cause is unknown. The workflow did not produce a report, claims, or final citations. Later
deterministic Web and Combined integration tests passed with fixture inference, but I did
not repeat local-Qwen Web or run local-Qwen Combined because the shared sufficiency path
had no proven fix.

### 11. What would you improve next?

I would first use a separate development set to diagnose local structured-output failures
and latency, changing one factor at a time. I would then freeze those changes and evaluate
them on a fresh untouched final test set. I would not tune against held-out labels. Only
after the local Web workflow is stable would I request a separately bounded live-source
acceptance test.

### 12. What security limitations remain?

This is an unauthenticated single-user localhost tool, not a production multi-user service.
It should not be exposed publicly. Further work would need authentication, stronger
workspace authorization, egress controls, parser isolation, retention decisions, and
broader evaluation.

### 13. What parts did you implement and validate?

The project includes the document ingestion and retrieval path, LangGraph stages, FastAPI
services, persistence models, citation and evidence checks, and the Next.js interface. The
automated checks cover deterministic workflow behavior, PostgreSQL/Qdrant integration, and
browser flows. I also have saved local-Qwen evidence for one cited answer and one safe
abstention. I distinguish those from the fixture-based Web/Combined tests, because the
real-Qwen Web run failed at sufficiency and real-Qwen Combined was not completed.

## Phrases to avoid

- “It guarantees factual answers.”
- “It has perfect citations or verification.”
- “Web and Combined are proven.”
- “The model never makes false claims.”
- “The benchmark proves high accuracy.”
- “It is production-ready for multiple users.”

Prefer bounded statements such as “the backend enforces exact quote and source-ID checks”
or “one local document run completed with a page citation.”
