# ResearchForge AI — Resume Bullets

Choose the three bullets that fit the role. They describe implemented work and bounded
validation; they do not claim production deployment or reliable Web/Combined inference.

- Built a local-first Agentic AI research assistant with Next.js, FastAPI, LangGraph, PostgreSQL, Qdrant, and Ollama, turning selected documents into saved, inspectable research reports.
- Implemented hybrid document RAG with BM25Plus, cached embeddings, Qdrant, and reciprocal-rank fusion, preserving page-level source provenance through report citations.
- Added per-fact evidence sufficiency, safe abstention, exact-quote and source-ID validation, and claim-support checks; demonstrated a local `qwen3:8b` answer with a page citation and a separate unanswerable-question abstention.

## Optional validation detail

Previously recorded automated checks: 185 backend unit tests, 232 PostgreSQL/Qdrant
integration tests (3 optional cached-model evaluations skipped), 39 frontend tests, and 5
browser tests passed. Deterministic offline Web and Combined integrations passed with
fixture inference. Real-Qwen Web stopped at sufficiency with an Ollama HTTP 500; real-Qwen
Combined has not been validated end to end. These results are documented in the
[completion checkpoint](FINAL_COMPLETION_STATUS.md).
