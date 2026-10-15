# Troubleshoot a failed run

## Trial AI access

An account without AI access may return errors such as:

| Operation | Error |
| --- | --- |
| Native PDF parsing | 399258: `_AI_PARSE_DOCUMENT` unavailable for trial accounts |
| Search index embedding | 399258: `EMBED_TEXT_1024` unavailable for trial accounts |
| Semantic filtering | 399258: `_AI_FILTER_WITH_PROMPT` unavailable for trial accounts |
| Model inference | 399258: `_COMPLETE_WITH_PROMPT_HISTORY_LLM` unavailable for trial accounts |
| Native Agent execution | 399504: access denied for trial accounts |

Role changes do not resolve these account eligibility errors. According to
[Snowflake's trial documentation](https://docs.snowflake.com/en/user-guide/admin-trial-account#current-limitations-for-trial-accounts),
an administrator can enable AI by adding a credit card. Adding a card alone does
not upgrade the account or end the trial. Check the live billing UI before
making a billing change; the demo does not change payment information.

Once AI is enabled, follow [continue after AI access](operate.md#continue-after-ai-access-is-enabled).
Do not switch to local extraction to claim native ingestion success. Resolve
AI access before running the native pipeline.

## A model is in legacy state

Error 512513 can mean a named model no longer accepts first use by this account.
The diagnostic now uses `claude-haiku-4-5`; the agent uses automatic model selection.
Check [model lifecycle and availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability)
before replacing a retired model. A legacy-model failure is separate from trial eligibility.

## A long query is cancelled after about a minute

The Python connector uses its network timeout as the query cancellation timeout
when `execute()` has no explicit timeout. The demo now passes 900 seconds to
`execute()`, matching its server statement limit, while retaining 60-second login
and network settings. Cancellation can be reported as error 000604.
See the [connector query timeout example](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-example).

## macOS Keychain

If authentication appears to stall, first test the existing profile with
`snow connection test -c YOUR_CONNECTION`. A newly installed Python interpreter
may need its own Keychain access approval. Handle OS prompts yourself according
to your local policy; keep credentials in the existing authentication mechanism.

Do not disable TLS or copy tokens into the repository. Diagnose the interpreter
and connector environment if the CLI succeeds but Python does not. Use the
supported Python 3.11–3.13 range and locked dependencies.

## Missing source, empty page, or mismatched hash

Keep the failed evidence. Move the specifically identified damaged local original
outside the corpus directory, then run `download` to fetch it again. Existing
files are checked and reused; `download` does not overwrite a corrupt file.
Inspect the original page. A blank extraction may need OCR or a different parser;
neither a missing page nor an unsupported file should be silently omitted.

Do not edit the local manifest to make validation pass. It is compared against
the authoritative Git tree. Repeated ingestion also checks each staged file's
actual bytes, including files that Snowflake reports as skipped uploads.

## Deployment or runtime verification fails

Inspect `~/.local/state/snow-analytical-search/failures/` for Snowflake query IDs and errors. A service may
take time to initialize; inspect its indexing error and retry `deploy` once the
underlying cause is fixed. There is no automatic retry loop that repeatedly
spends AI credits.

If `verify-runtime` cannot confirm the native context aggregate and matching
query history, stop analytical evaluation and inspect the saved answer. The probe
reads only its same-run Search `RESULT_SCAN`; it does not request base-table
inventory or a separate session-only query. Do not infer execution context from
the agent's prose or from the client connection alone.

A successful tool response may omit `resultSetMetaData.rowType`. The verifier
uses the cached native query result through same-user `RESULT_SCAN` to obtain
column names. It never guesses positional columns or reruns AI SQL. Unknown or
missing secondary-role context fails verification.

For a UI/API discrepancy, compare the same LIVE specification and question.
The stored default version can differ from Studio's LIVE draft. Snowflake documents
an explicit [versioned REST endpoint](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-versioning)
and [role/warehouse request headers](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/setting-context).
Check the actual child queries, not just those requested settings. Preserve raw
JSON or streaming events privately; do not replay an ambiguously completed request
automatically. In the recorded comparison, both REST modes remained Search-only.

Do not add an undocumented `base_table` field, spoof Studio as the request origin,
or broaden permissions to force a pass. See the current
[execution-path results](../reference/capabilities.md#native-analytical-execution).

## An answer is missing or suspicious

Inspect the newest `~/.local/state/snow-analytical-search/answers/` file. It includes raw response content,
annotations, tool results, elapsed time, and query ID. Errors, warnings, empty answers and interrupted completion statuses fail
the command. SQL exceptions during an agent call are also
preserved. Raw responses are saved before parsing; malformed content records a
`parse_error` without discarding the original. A failure before the connection is established may produce only the
command-level diagnostic.

For counts, compare against the manifest and check `COUNT(DISTINCT DOC_ID)`.
For source facts, open the original PDF at the physical page number or the
commit-pinned Markdown/JSON source. Text extraction can distort spacing and
tables; inspect visual evidence before making a visual claim.
