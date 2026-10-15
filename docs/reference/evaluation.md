# Questions and evaluation

The suite contains six questions after a bounded native runtime check. The
recorded programmatic gate still fails because no native SQL result is returned.
Studio has demonstrated bounded native analysis, so this is an execution-path
limitation rather than evidence that the account cannot use Analytical Search.
Separate diagnostic questions assess answer quality without overriding that gate.
See [capabilities and limits](capabilities.md) for the verified scope.

## Questions and acceptance criteria

| Case | Question | What to check |
| --- | --- | --- |
| Zava vacation | What vacation tiers exist, how long is each, and what extra benefit accompanies each? | Standard: 2 weeks and health/wellness stipend; Senior: 4 weeks and travel vouchers; Executive: 6 weeks and family resort getaway. Cite the company overview. |
| Inventory | Count every distinct file by type and list all paths, including query examples. | Exactly 13 `(DOC_ID, SOURCE_PATH, FILE_TYPE)` rows: 7 PDFs, 5 JSON, 1 Markdown. Compare the exact verified manifest set; matching totals alone cannot pass. |
| Semantic analysis | Which distinct documents discuss mental health support or benefits? Use Search, AI_FILTER, then distinct-document counts. | Expect four PDFs: Benefit Options, Health Plus, Standard and PerksPlus. Include clinical benefits, exclusions and nonclinical support. Inspect native SQL, the predicate, deduplication, supporting passages and candidate coverage. Do not equate mentioning a benefit with providing coverage. |
| Plan comparison | Compare Northwind Standard and Health Plus on prescriptions and specialists. | Cite each plan's own pages, preserve exceptions, and report contradictions instead of inventing a unified policy. |
| JSON work item | What does item 2190 request, and what are its State and Tags? | Sending guest confirmations; `State=New`; `Tags=Notification`; cite `Json_Examples/2190.json`. |
| Unsupported fact | What is the exact 2026 annual salary of Zava's CEO? | State that the corpus does not establish this value. Do not invent a salary or use the role description as salary evidence. |

Source expectations were checked against the pinned
[company overview](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/data/Zava_Company_Overview.md),
[work item](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/data/Json_Examples/2190.json),
manifest, and representative original PDF pages. These fictional documents can
contradict each other; they are not real employment, healthcare, or financial advice.

## Runtime and native execution evidence

`verify-runtime` asks for one Search result containing at most ten passages and
one native SQL statement over `RESULT_SCAN` of that exact query ID. The statement
counts passages and distinct documents while projecting `CURRENT_USER()`,
`CURRENT_ROLE()`, `CURRENT_SECONDARY_ROLES()` and `CURRENT_WAREHOUSE()`.
It does not request a Base Table or separate identity-only query.

The verifier confirms the reported SQL against same-user query history: query ID,
user, primary role, warehouse, success, exact SQL text and timestamps within this
run. It then reads the stored native result with `RESULT_SCAN`. Optional response
column metadata may be absent; no column positions are guessed and the model's
SQL is never executed by the verifier. Unknown secondary-role context fails.

Each question receives its own audit. A successful runtime probe does not prove
the context of later calls. Their secondary roles remain explicitly unverified
unless separately evidenced for that call.

Enabling the capability or receiving a plausible answer is insufficient.
Native analytical evidence requires matched tool-use/result IDs, successful
persisted results from the configured Search tool, and later native SQL applying
`AI_FILTER`, `AI_EXTRACT` or `AI_AGG` to that same-run result or a verified
intermediate result. The actual child queries and stored results are checked
independently. Search-only answers, failed calls, unrelated SQL and inline strings
containing function names do not establish analytical acceptance.

Before each call the client reads LIVE and checks the generated specification,
including instructions and the snapshot service binding.
It records the specification fingerprint and raw-response hash. Raw evidence is
saved before parsing; a malformed response retains a `parse_error` instead of
disappearing. Warnings, errors, empty answers and interrupted statuses fail.

Lineage detection remains a necessary signal, not a full SQL semantics proof.
Review whether the AI predicate actually consumes the candidate text and whether
counts deduplicate `DOC_ID`. The suite retains `requires_human_answer_review=true`;
its highest automatic result is `requires_review`, not accepted accuracy.

## Coverage and citation review

`verify` reconciles the entire Search index with the corpus using
[`CORTEX_SEARCH_DATA_SCAN`](https://docs.snowflake.com/en/sql-reference/functions/cortex_search_data_scan).
It compares every chunk's ID, text and provenance, and rejects missing, duplicate,
extra or changed rows. This audit runs as OWNER. RUNNER separately checks that
each source is retrievable.

The inventory question must return a native SQL result containing the exact
manifest `(DOC_ID, SOURCE_PATH, FILE_TYPE)` set, including query examples.
A correct total with a missing and an invented file fails.

For semantic analysis, the audit records distinct persisted Search candidate chunk
IDs available to native SQL and compares
them with all eligible snapshot chunks, excluding query examples. A limit of 1000
and 281 indexed rows do not prove that Search returned all eligible candidates.
Ordinary Search passages can support document Q&A but do not establish this
native SQL candidate chain. If persisted coverage is incomplete, describe the
analysis as bounded. Even complete candidate
coverage requires review of the AI predicate, false positives and omissions.
The broad question includes discussion of exclusions and nonclinical support;
mentioning a benefit does not establish that a plan covers it.

Citation checks resolve the configured chunk ID to its source version, stage path,
filename and physical page, and validate rebased answer offsets. This establishes
traceability only. Review each claim against the original physical page or pinned
Markdown/JSON file. Check contradictory statements and omitted qualifications.

The financial report contains charts. Native LAYOUT preserves prose and tables;
filtered native OCR recovers printed chart labels that LAYOUT omitted. Neither
establishes relationships between labels, axes, and plotted
marks. A chart-value or diagram-direction question needs a separate visual
evaluation and is outside this suite's demonstrated capability.

## Record a completed run

For each case, record the answer, elapsed time, native tool traces, citation
checks, expected-versus-observed result, and a pass/fail/uncertain verdict.
Bind each review verdict to the recorded raw-response hash. Preserve failures and
source conflicts. Do not replace them with hand-written
answers and label those as agent output.

The [capability reference](capabilities.md) records the verified scope and
remaining native-analysis limitation. Keep account-specific run reports private.
