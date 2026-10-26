# Third-party content and fixture provenance

The offline Web and Combined regression fixtures now use original synthetic text. The
synthetic passage in `backend/tests/test_execution_postgres.py` is explicitly labeled as a
training note written for testing, and its URL uses the reserved `.invalid` domain. The
UI test uses separately written synthetic text and the same reserved test domain. Neither
fixture represents a real web result or is presented as Wikipedia evidence.

The previous copied article passage was removed from the bundled tests. The historical
record in [`docs/LIVE_WEB_COMBINED_ACCEPTANCE.md`](../docs/LIVE_WEB_COMBINED_ACCEPTANCE.md)
is retained to document what happened during the earlier acceptance run. It records source
titles, URLs, and outcome summaries; it is not a replay fixture, does not contain the full
retrieved article passage, and must not be represented as a current passing test.

The application still includes an optional live English Wikipedia adapter. If that feature
is used, article text is subject to its applicable page license and attribution terms; the
adapter preserves the source title and link in research records. This repository does not
bundle Wikipedia article text in its current test fixtures. Other external sources and
non-text media can have different licenses.
