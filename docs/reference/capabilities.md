# Capabilities and limits

The implementation validates each stage separately. A successful answer does
not prove complete retrieval, correct citations or native SQL execution.

## Verified ingestion behavior

For the [pinned sample corpus](corpus.md), native ingestion produced 13 documents,
279 pages and 281 chunks. It used `AI_PARSE_DOCUMENT` in LAYOUT mode for all seven
PDFs, native OCR on nine pages containing image references, and Snowflake's
recursive character splitter for every file. An unchanged rerun reused all files.

Checks cover original hashes, uploaded-byte read-back, physical page counts,
complete page-text coverage, stored rows and retrieval of every source. Native
extraction recovered the paycheck-cost table in `Benefit_Options.pdf` physical
page 4 that local extraction had omitted.

These measured counts are a baseline, not values to hardcode into a new run.
Parser changes can alter extracted text and chunk boundaries. Never repair a
failed validation by editing the source manifest or filling gaps manually.

## Answer quality

Source review of diagnostic questions confirmed vacation tiers, work-item fields,
all six paycheck-cost amounts, two financial correlation values and printed chart
labels. The agent correctly declined an unsupported CEO-salary question.
Mental-health retrieval found all four relevant PDFs and retained a policy
contradiction within the Standard plan.

Two limitations matter when evaluating a new deployment:

- An inventory answer missed one file despite all 13 being indexed. A follow-up
  correctly labelled its ranked results as a non-exhaustive sample. Use verified
  SQL aggregation for a complete count.
- A benefits comparison missed a specialty-drug prior-authorization qualifier
  present in the detailed source. Resolvable citations alone do not prove every
  relevant condition has been included.

## Native analytical execution

**Full Analytical Search acceptance has not passed in the recorded evaluation.**
The configured agent invoked analytical routing but lacked the implicit
`system_execute_sql` tool. Ordinary document Q&A and AI prerequisite calls worked;
no substitute Python or custom SQL tool was used to claim native success.

Run `verify-runtime` and `evaluate` in your environment. Accept analytical results
only after successful native SQL, search-to-AI lineage and source review. If the
implicit tool remains unavailable, retain the private evidence and investigate
with Snowflake; do not present a model's manual tally as a SQL result.

See [the evaluation rubric](evaluation.md) and
[Snowflake's Analytical Search documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-analytical-search).

## Visual evidence

LAYOUT preserves prose and tables; OCR recovers printed image labels. Neither
proves plotted point values, arrow directions or unprinted percentages. Inspect
original visuals before answering questions about those relationships.
