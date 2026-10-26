# Phase 3 — document intelligence and hybrid retrieval

The local implementation supports PDF, DOCX, UTF-8 TXT and Markdown. It stores actual
uploaded passages and tests against actual PostgreSQL and Qdrant. Mock report writing
is an extractive demonstration, not evaluated research synthesis. English is the
supported embedding language; multilingual retrieval and OCR are not implemented.

## Start and demonstrate on macOS

From `/path/to/researchforge-ai`:

```bash
docker compose --profile infrastructure up -d postgres qdrant
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
# Explicit download only if the pinned small model is not already cached:
backend/.venv/bin/python scripts/download_embeddings.py
RF_LLM_PROVIDER=mock RF_SEARCH_PROVIDER=mock RF_LIVE_CALLS_APPROVED=false \
RF_EMBEDDING_PROVIDER=local backend/.venv/bin/python -m uvicorn app.main:app \
  --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```bash
cd /path/to/researchforge-ai/frontend
NEXT_TELEMETRY_DISABLED=1 npm run dev
```

Open http://127.0.0.1:3000. Upload a small text document containing, for example,
“The Juniper battery stores 20 kWh. Inspection is required every 30 days.” Wait for
**ready / indexed**, select it, select Documents mode, save a question about Juniper,
and explicitly run the mock demonstration. Inspect the actual passage, document ID,
chunk ID, and page (PDF only). No web search runs in Documents mode. DOCX has no stable
pagination: paragraph/table headings are retained, page is unavailable.

Combined mode retrieves documents first, reserving source slots for web evidence. It
warns if none are ready. Web mode keeps the existing bounded web path. No document
selection means all ready documents in the local workspace; explicit IDs narrow retrieval.
Selections are stored with the session. Foreign/unready IDs cannot be attached.

## Concepts and implementation map

1. An **embedding** is a numeric representation of text. Similar meaning can produce
   nearby vectors. `app/documents/embeddings.py` uses FastEmbed/ONNX, BGE small English,
   384 dimensions, CPU with two threads and batches of eight. No Torch/CUDA dependency.
   The fake 64-dimensional hashed-token provider is deterministic and has no semantic
   quality claim. Fake and local collections are separate.
2. **Chunking** splits extracted pages into at most 1,000-character passages with
   150-character overlap, preferring spaces. It never crosses PDF pages. Smaller chunks
   give precise references but can lose context; larger chunks cost more context and
   can mix topics. Character limits are not exact token limits. The model truncates
   beyond 512 tokens, particularly relevant to unusual Unicode-heavy inputs. Stable UUID5
   IDs include document/page/start/content hash. Repeated identical chunks on the same
   page are removed; identical text on different pages keeps its provenance.
3. **Qdrant** stores vectors. `vectors.py` checks collection dimensions and cosine metric,
   inserts in batches with wait=true, confirms count, and filters workspace/document IDs.
   `service.py` only commits readiness after this and PostgreSQL chunk persistence succeed.
4. **BM25** ranks token overlap with corpus frequency and passage length normalization.
   `retrieval.py` uses established rank-bm25, Unicode word tokenization, and a bounded
   authorized corpus. It is rebuilt from PostgreSQL on each search: no stale in-memory
   index to update. At most 12,000 chunks are loaded; larger corpora fail explicitly.
5. **Hybrid search** fuses the top 20 keyword and semantic candidates with reciprocal
   rank fusion: sum `1/(60+rank)`. The raw scores stay separate; unlike scores are not
   directly added. Chunk IDs deduplicate the merged list. At most eight passages return.
6. **LangGraph** calls the structured document retrieval service in its collection node.
   It passes question, authorized document IDs and a bounded K; it sends excerpts to the
   writer rather than whole documents. Retrieved text is untrusted evidence.
7. **Citations** use the run's S1–S8 evidence IDs, bound to the session, document UUID,
   chunk UUID/hash and page. Markdown references and the UI use stored metadata, never
   generated file paths. Source-ID existence does not establish semantic support.
8. **Testing** commands appear below. `tests/test_documents_postgres.py` exercises real
   Qdrant plus PostgreSQL, including generated two-page PDF provenance, reindex/delete,
   workspace filters, invalid uploads, explicit vector-store failure and document research.
9. Study `parsing.py` → `embeddings.py` → `vectors.py` → `retrieval.py` → `service.py`
   → `api/documents.py` → `research/workflow.py`; UI: `document-workspace.tsx` and
   `run-panel.tsx`. Paths are under backend/app and frontend/src respectively.

## Storage and failure model

The raw upload API is `POST /api/v1/documents/upload`, binary content type, percent-encoded
`X-Filename`. GET collection/detail doubles as ingestion-status access. POST
`/{id}/reindex` and `/{id}/delete` use JSON. POST `/retrieve` accepts question,
document_ids, k and method (semantic/bm25/hybrid).

Files are private, UUID-named, outside the served frontend directory, under `data/documents`.
The application enforces 5 MB/file, 30 active documents, 100 PDF pages, 250,000 extracted
characters, 400 chunks/document, DOCX ZIP expansion limits, signature and parser checks.
Storage uses an exclusive temporary file, fsync, atomic rename and cleanup on failed
acceptance. Do not manually edit storage files. Extension/MIME alone are insufficient.
Parser subprocesses have CPU and wall deadlines and no application credentials. They
are not an OS security sandbox; macOS memory limits are not reliably enforceable. Only
trusted local files should be processed until deployment-grade isolation/scanning exists.

Lifecycle: queued → processing/indexing → ready/indexed, or failed/incomplete.
No PostgreSQL/Qdrant distributed transaction exists. Every reindex hides the document,
changes its generation, deletes old vectors, overwrites deterministic points and replaces
chunks before readiness. Failures retain metadata for explicit retry; abandoned vectors
are excluded by the authoritative PostgreSQL ready/generation filter. Startup interrupts
unfinished jobs; it never silently replays them. One local document job runs at a time,
with no queue. Keep one API worker. Shutdown cancels parser work; failed indexing is
never successful ingestion. External outages may delay failure persistence until restart.

Deletion hides the document before vector/file removal, then removes chunks and keeps a
metadata tombstone. Partial deletion is explicit and retryable. Active document research
blocks reindex/deletion. Old completed reports retain immutable passage snapshots: deleting
a document is not full erasure from reports/backups. Reupload after completed deletion is
allowed. Original filename/checksum tombstones remain. No retention scheduler, encryption
at rest, authentication, virus scanner, OCR or arbitrary-host-file download endpoint exists.

## Evaluation and commands

```bash
bash scripts/check.sh
backend/.venv/bin/python scripts/test_database.py
backend/.venv/bin/python scripts/test_database.py --browser
RF_RUN_LOCAL_EVALUATION=1 backend/.venv/bin/python scripts/test_database.py -k local_retrieval_evaluation
backend/.venv/bin/alembic -c backend/alembic.ini check
docker compose --env-file .env.example --profile infrastructure config --quiet
```

Tests force fake embeddings and never download a model. The opt-in evaluation uses only
the already cached pinned model, real Qdrant and a disposable PostgreSQL database.
`evaluation/phase-3-results.json` records generated corpus, relevance labels, Recall@3,
MRR@3, nDCG@3, per-query retrieval and indexing milliseconds, chunks and uploaded bytes.
All three methods achieved 1.0 on six easy examples; this does not demonstrate superiority
or generalize to representative research. No reranker was justified. Timings include API
and database overhead and one small local run, not a load benchmark.

The quantized MIT model is listed at 0.067 GB; actual cache allocation measured ~64 MiB.
The pinned HF revision is `aa8f8b060edb00e03bfdd08813a2949946c8ba55`. pypdf is BSD-3-Clause,
python-docx MIT, FastEmbed Apache-2.0, rank-bm25 Apache-2.0, Qdrant Apache-2.0. Review
transitive licenses for distribution. No AGPL PDF dependency was introduced.

References: [FastEmbed](https://qdrant.tech/documentation/fastembed/fastembed-quickstart/),
[collections](https://qdrant.tech/documentation/manage-data/collections/),
[pypdf extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
