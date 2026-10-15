# Questions and evaluation

The suite contains six questions plus a native SQL-context check. AI access is
enabled and document Q&A runs. **The full evaluation remains unaccepted:** the
runtime check cannot execute its identity SQL through the agent's implicit tool.
Separate diagnostic questions assess answer quality without overriding that gate.
See [capabilities and limits](capabilities.md) for the verified scope.

## Questions and acceptance criteria

| Case | Question | What to check |
| --- | --- | --- |
| Zava vacation | What vacation tiers exist, how long is each, and what extra benefit accompanies each? | Standard: 2 weeks and health/wellness stipend; Senior: 4 weeks and travel vouchers; Executive: 6 weeks and family resort getaway. Cite the company overview. |
| Inventory | Count every distinct file by type and list all paths, including query examples. | Exactly 13 paths, 7 PDFs, 5 JSON, 1 Markdown. Compare independent manifest SQL. |
| Semantic analysis | Which distinct documents discuss mental health support or benefits? Use Search, AI_FILTER, then distinct-document counts. | Inspect successful native SQL, the search service/version, semantic predicate, deduplication, supporting passages, and retrieval coverage. Do not equate mentioning a benefit with providing coverage. |
| Plan comparison | Compare Northwind Standard and Health Plus on prescriptions and specialists. | Cite each plan's own pages, preserve exceptions, and report contradictions instead of inventing a unified policy. |
| JSON work item | What does item 2190 request, and what are its State and Tags? | Sending guest confirmations; `State=New`; `Tags=Notification`; cite `Json_Examples/2190.json`. |
| Unsupported fact | What is the exact 2026 annual salary of Zava's CEO? | State that the corpus does not establish this value. Do not invent a salary or use the role description as salary evidence. |

Source expectations were checked against the pinned
[company overview](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/data/Zava_Company_Overview.md),
[work item](https://github.com/Azure-Samples/azure-search-openai-demo/blob/558ffd397eddcfe4da5c85ebc285796b367eb9b2/data/Json_Examples/2190.json),
manifest, and representative original PDF pages. These fictional documents can
contradict each other; they are not real employment, healthcare, or financial advice.

## What counts as Analytical Search evidence

Enabling the capability or receiving a plausible answer is insufficient.
The automated trace check accepts two native response shapes:

- Successful `system_execute_sql` statements containing the configured Search
  service, `SEARCH_PREVIEW`, and an AI function.
- A successful configured `corpus_search` result with a persisted search query ID,
  followed by successful native SQL applying `AI_FILTER`, `AI_EXTRACT`, or `AI_AGG`
  through `RESULT_SCAN` of that query or a linked intermediate result.

Before each agent call, the client reads the live agent specification and verifies
that `corpus_search` binds to the configured snapshot service. This matters because
the native persisted-search SQL uses bound parameters instead of a literal service
name. Search-only results and unrelated AI SQL do not satisfy the linked-flow check.

That check is a necessary signal, not a proof of correct data flow. Review the
actual statements and returned rows: confirm that the AI operation consumes the
retrieved candidates and that counts deduplicate `DOC_ID`. A string in an answer,
a failed SQL call, or a plain manifest `COUNT` is not native analytical proof.

The suite independently runs manifest SQL for the inventory baseline. It sets
`requires_human_answer_review=true` even after passing its trace check.

## Coverage and citation review

For each claimed fact, verify the cited filename and physical page against the
original. Check that the source version matches the active snapshot. A chunk ID
alone is traceable to a passage, but it does not guarantee that a generated claim
is supported by that passage.

For exhaustive semantic lists, inspect the candidate count and tail of search
results. Use the active snapshot's measured chunk count from the capability reference,
and compare it with the configured limit of 1000. That limit alone does not
prove every relevant chunk was retrieved. Compare
against the full page/chunk tables and explain any uncertain cases.

The financial report contains charts. Native LAYOUT preserves prose and tables;
filtered native OCR recovers printed chart labels that LAYOUT omitted. Neither
establishes relationships between labels, axes, and plotted
marks. A chart-value or diagram-direction question needs a separate visual
evaluation and is outside this suite's demonstrated capability.

## Record a completed run

For each case, record the answer, elapsed time, native tool traces, citation
checks, expected-versus-observed result, and a pass/fail/uncertain verdict.
Preserve failures and source conflicts. Do not replace them with hand-written
answers and label those as agent output.

The [capability reference](capabilities.md) records the verified scope and
remaining native-analysis limitation. Keep account-specific run reports private.
