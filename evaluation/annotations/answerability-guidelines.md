# Answerability annotation guide

`datasets/answerability-v1.json` contains 6 development and 12 held-out synthetic
questions. It is a review starter set, not a curated real-world benchmark. Every record is
marked `unreviewed`; no reviewer or agreement result is implied.

For each question, decide whether the supplied passages directly support all material
parts (`SUFFICIENT`), some but not all (`PARTIAL`), materially incompatible answers
(`CONFLICTING`), or no reliable answer (`INSUFFICIENT`). Record exact passage IDs and
short fact labels. A related topic, shared entity name, or matching keyword is not support.
Check entities, units, quantities, dates, scope, negation and references such as “it”. A
question with missing context is insufficient even when a passage is topically related.

## Review workflow

Generate the editable review sheet:

```bash
backend/.venv/bin/python scripts/evaluate_answerability.py
open evaluation/annotations/answerability-review.csv
```

The CSV deliberately preserves expected labels for audit. For an independent first pass,
make a review copy and temporarily hide `expected_answerability`, `relevant_passage_ids`,
`required_facts` and `expected_missing_facts`. Review the 12 `held_out` rows first; this is
a manageable initial batch. Enter the reviewer’s own label in a new column, add evidence
IDs and notes, and mark `review_status=reviewed` only after a person checked the excerpt.
Enter disagreement details when reviewers differ. Keep the source CSV unchanged and store
reviewed copies separately; do not overwrite the machine-readable benchmark labels.

After two independent reviews, compare labels row by row and resolve disagreements with
a third adjudicator or retain the disagreement as unresolved. Record reviewer names only
with their consent and report agreement only after computing it from the completed,
independent labels. Until then, keep every record unreviewed and do not call results
human-validated.
