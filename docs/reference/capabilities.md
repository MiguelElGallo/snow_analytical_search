# Capabilities and limits

The implementation validates each stage separately. A successful answer does
not prove complete retrieval, correct citations or native SQL execution.

## Verified ingestion behavior

For the [pinned sample corpus](corpus.md), native ingestion produced 13 documents,
279 pages and 281 chunks. It used `AI_PARSE_DOCUMENT` in LAYOUT mode for all seven
PDFs, native OCR on nine pages containing image references, and Snowflake's
recursive character splitter for every file. An unchanged rerun reused all files.

Checks cover original hashes, uploaded-byte read-back, physical page counts,
complete page-text coverage, stored rows and retrieval of every source. The latest
index audit also reconciled all 281 indexed chunk IDs, text and provenance with
the corpus using `CORTEX_SEARCH_DATA_SCAN`; equal row counts alone are insufficient.
Native extraction recovered the paycheck-cost table in `Benefit_Options.pdf` physical
page 4 that local extraction had omitted.

These measured counts are a baseline, not values to hardcode into a new run.
Parser changes can alter extracted text and chunk boundaries. Never repair a
failed validation by editing the source manifest or filling gaps manually.

## Answer quality

The final six-question diagnostic on **2026-10-15** was reviewed against the
pinned sources. Its runtime gate failed, so these are answer-quality findings,
not an accepted end-to-end analytical evaluation.

| Question | Source-review result |
| --- | --- |
| Vacation tiers | Passed: all three tiers, durations and extra benefits match |
| Complete inventory | Unanswered: the agent reported unavailable native SQL; its persisted candidates covered only 12 of 13 files |
| Mental-health discussion | Incomplete: three of the four qualifying PDFs were listed; `Benefit_Options.pdf` physical page 3 was omitted |
| Plan comparison | Failed: source exceptions and contradictions were missed, a Standard-plan requirement was attributed to Health Plus, and an unsupported reconciliation was added |
| Work item 2190 | Passed: request, state and tags match |
| CEO salary | Passed: the agent correctly declined the unsupported fact |

All 48 citation identities and answer offsets resolved. That did not make the
comparison accurate or the semantic answer complete. General instructions to
preserve exceptions and compare each plan independently did not resolve these
failures in the retest.

Earlier diagnostics correctly returned all six paycheck-cost amounts, two
financial correlation values, printed chart labels and four mental-health PDFs.
Those historical successes do not supersede the final-suite omissions. The
independent source review covers all 13 files; four PDFs discuss mental-health
benefits, exclusions or nonclinical support.

For complete inventory or semantic counts, verify both native SQL execution and
the exact candidate set. SQL aggregation over an incomplete Search result cannot
recover missing files. Review each claim against its source even when citations
resolve correctly.

## Native analytical execution

**Full Analytical Search acceptance has not passed in the recorded evaluation.**
The checks on **2026-10-15** distinguish these execution paths:

| Path | Observed result | What it establishes |
| --- | --- | --- |
| Agent Studio Preview in Edge | Native Search → `RESULT_SCAN` → SQL counts and `AI_FILTER`; the final diagnostic analyzed 97 chunks from four documents | Native analytical execution works for a bounded sample in Studio |
| Repository SQL helper, explicit `LIVE` | Persisted Search succeeded; no native SQL tool result | The repository runtime gate remains failed |
| Versioned `LIVE` REST, JSON and streaming | Persisted Search succeeded with the requested role and warehouse; no native SQL tool result | Switching transport or streaming mode did not resolve the difference |

The Studio AI-filter example examined ten retrieved passages, matched nine and
counted two distinct documents. That is a bounded result, not a corpus-wide
answer. A later native context query confirmed that Studio used the default
warehouse and all available secondary roles. It does not certify the repository's
restricted runtime context. A further REST diagnostic with that same existing
role/warehouse context still returned no native SQL result, so those settings
alone did not resolve the UI/API difference. Its precise cause remains unresolved.

The final Studio diagnostic requested up to 1000 candidates but returned only
97 of the 281 indexed chunks, all from four PDFs. Stored native query results
confirmed the counts and per-document `AI_FILTER` output. It found the four
expected documents within that sample; it did not demonstrate exhaustive
retrieval. A scalar classification returned 39 matching passages and a later
per-document classification with a changed predicate returned 49. These are
different classifier outputs; the difference does not establish nondeterminism.
The final SQL also invoked `AI_FILTER` separately for counts and supporting pages
without retaining one classification per chunk. Neither passage count is accepted
as verified accuracy.

The initial transport comparison used one unchanged LIVE specification. Later
retests used revised instructions that removed references to an unconfigured
Base Table and strengthened source-comparison guidance; the SQL/REST limitation
persisted. No undocumented Base Table field, custom SQL tool, broader grants or
manually executed model SQL was added to make the gate pass.

Run `verify-runtime` and `evaluate` in your environment. Accept analytical results
only after verified native query history, same-run Search-to-AI lineage, coverage
checks and source review. Retain private failure evidence if the native tool is
absent. Never treat a model's manual tally as a SQL result.

See [the evaluation rubric](evaluation.md) and
[Snowflake's Analytical Search documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-analytical-search).

## Visual evidence

LAYOUT preserves prose and tables; OCR recovers printed image labels. Neither
proves plotted point values, arrow directions or unprinted percentages. Inspect
original visuals before answering questions about those relationships.
