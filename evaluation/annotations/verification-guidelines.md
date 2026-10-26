# Verification annotation notes

The Phase 5 fixtures are synthetic and policy-curated. Their labels are provisional;
no independent human review has occurred. Do not describe them as human-verified.

For a future reviewed set, annotators should apply these rules independently before
adjudication:

- **Supported:** the cited passage directly entails the complete, checkable claim in
  the same scope, entity, time period, and units. Mere word overlap does not count.
- **Contradicted:** a cited passage states an incompatible value or proposition in the
  same context and period. A different date, population, prototype, or measurement may
  make the case ambiguous instead.
- **Insufficient evidence:** the passage is unrelated, only a near match, incomplete,
  does not cover every clause, or sources conflict without enough context to resolve it.
- **Not evaluated:** the text is a fragment, question, instruction, subjective opinion,
  or cannot be checked as a proposition. Preserve the original text and record why it
  was excluded.
- **Time-dependent claims:** record the relevant date or period. Current information
  must be checked against an appropriately current source; retrieval time is not
  publication time.
- **Conflicting evidence:** retain each source and its context. Do not choose the newer
  passage or treat the number of sources as a reliability score.
- **Citation correctness:** check ID, session, document, passage, page and freshness
  independently from whether the passage supports the claim. Citation existence is not
  factual correctness.

Each annotation should preserve the exact claim, cited passage IDs, relevant quote,
label, reason, annotator, and adjudication state. Never include user documents or secrets
in the public evaluation corpus.
