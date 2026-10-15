# Configuration and CLI

All commands run from the repository root. The default configuration is
`~/.config/snow-analytical-search/demo.toml`; use `sas --config /path/outside/repo/demo.toml COMMAND` to select another
file. The `--config` option goes before the command.

## Configuration

| Field | Meaning |
| --- | --- |
| `connection` | Existing named profile in Snowflake's connection configuration |
| `expected_account` | Expected `CURRENT_ACCOUNT_NAME()`; every connection checks it |
| `prefix` | Uppercase resource prefix, at most 48 characters; default `SNOW_ANALYTICAL_SEARCH` |
| `source_commit` | Full lowercase 40-character commit SHA in the Azure sample repository |
| `state_dir` | Local evidence/cache directory, `~` expands to your home directory; relative paths resolve beside the config. Default: `~/.local/state/snow-analytical-search` |
| `native_ocr` | Boolean, default `true`; native OCR supplements only PDF pages with image references. `false` reproduces the native layout-only baseline. Ignored in historical local mode. |
| `pdf_parser` | `snowflake` (default): native PDF parsing and native splitting of every file. `local` preserves the historical offline preparation path; never selected silently after a failure |

The upstream repository is fixed in code as `Azure-Samples/azure-search-openai-demo`.
Changing the commit or parser changes the snapshot. Changing credentials is not
part of this configuration.

## Commands

Prefix each command below with `uv run sas`.

| Command | Effect | Role |
| --- | --- | --- |
| `preflight` | Report account, region, and cross-region setting | ACCOUNTADMIN |
| `download` | Fetch and verify the complete pinned `data/` tree and license | No Snowflake connection |
| `extract-pdfs` | Create/check local PDF page envelopes; verifies inventory through GitHub | No Snowflake connection |
| `setup` | Create dedicated roles, database, warehouse, schemas, stage, and tables | ACCOUNTADMIN, then OWNER |
| `ingest` | Upload/read back originals, parse or reuse pages, load and verify snapshot | OWNER |
| `check-ai` | Two small calls: AI_FILTER and AI_COMPLETE; save success or failure | RUNNER |
| `deploy` | Create versioned multi-index Search; verify corpus; create/update agent | OWNER and RUNNER |
| `verify --corpus-only` | Check the corpus without querying Search | OWNER |
| `verify` | Check corpus and retrieve every source from Search | OWNER and RUNNER |
| `verify-runtime` | Ask native agent for SQL identity; check results and query history | RUNNER |
| `ask "QUESTION"` | Run the stored agent and save the response | RUNNER |
| `evaluate` | Verify runtime context, then ask the six evaluation questions | RUNNER |
| `pause` | Suspend current Search indexing/serving if present, then warehouse | OWNER |
| `resume` | Resume the current Search service; fail if it does not exist | OWNER |

Commands exit nonzero on failure. `check-ai` is a prerequisite check, not proof
of Search readiness or a complete agent run. `evaluate` stops on a failed answer;
completed answers remain on disk and a failed report names the stage. The report
is updated even when the initial runtime or final analytical gate fails. Passing
automated checks produces `status=requires_review`, never an automatic quality
pass. A failed initial runtime check stops the suite before its questions.

`ask` preserves the raw response before rejecting errors, warnings, empty answers
or a present completion status other than `completed`. Cancelled and timed-out
partial answers therefore exit nonzero. Omitted/null status is accepted for
compatibility with observed SQL API responses; this does not bypass the other
checks or the separate native SQL acceptance gate.

## Resource names and limits

| Resource or setting | Value |
| --- | --- |
| Database | `<prefix>` |
| Warehouse | `<prefix>_WH`, X-Small, auto-suspend 60 seconds |
| Roles | `<prefix>_OWNER`, `<prefix>_RUNNER` |
| Stage | `<prefix>.RAW.DOCUMENTS`, internal SSE |
| Search | `<prefix>.APP.DOCUMENTS_<SNAPSHOT>` |
| Agent | `<prefix>.APP.CORPUS_AGENT` |
| Search text indexes | `CHUNK`, `DOC_ID` |
| Search vector index | `CHUNK`, `snowflake-arctic-embed-l-v2.0` |
| Search refresh | FULL, ON_CREATE, target lag one day |
| Search serving auto-suspend | 1800 seconds |
| Agent search result limit | 1000 chunks |
| Agent orchestration budget | 360 seconds, 32,000 tokens |
| SQL statement timeout | 900 seconds on both server and connector query execution; queue timeout 60 seconds |
| Native chunking | Snowflake recursive splitter; at most 3500 characters, up to 300-character overlap, within one page |

Orchestration limits are not a monetary budget. A search result is a chunk, not
necessarily a whole document. See [cost](../explanation/access-cost.md) and
[coverage](../explanation/architecture.md).

## Local evidence

Runtime evidence is written outside the checkout by default, under `state_dir`.
Keep this directory and personal configuration out of Git: responses and query
IDs can reveal private account or document details.

| Path below `state_dir` | Contents |
| --- | --- |
| `corpus/<commit>/` | Originals, authoritative manifest, upstream license |
| `parses/<snapshot>/<sha256>.json` | Raw LAYOUT or labelled composite page envelope, source/parser provenance and input references |
| `ocr/<snapshot>/<sha256>.json` | Raw native OCR, exact page filters, errors and query IDs |
| `chunks/<snapshot>/<doc_id>.json` | Unmodified native split rows, SQL, query ID and provenance |
| `snapshots/<snapshot>/` | Snapshot-bound ingestion reports and retained live-run audits |
| `extraction.json` | Historical local extraction's PDF page counts and parser identity |
| `ingestion.json` | Latest load verification, processed/reused counts |
| `corpus-verification.json` | Explicit corpus-only verification |
| `verification.json` | Corpus and indexed-source checks |
| `deployment.json` | Requested and read-back configuration, indexed sources |
| `capability-probes.json` | Minimal AI prerequisite results |
| `runtime-verification.json` | Native SQL-context verification result, including failed checks |
| `answers/*.json` | Raw response, citations, SQL traces, timing, and query ID |
| `evaluation.json` | Suite results or the failed question and partial results |
| `evaluations/*.json` | Timestamped suite reports, including failed runs |
| `failures/*.json` | Command-level Snowflake errors and query IDs |

Files for stages that have not succeeded may be absent. Evidence reports are
snapshots of individual runs, not an automatically updated service status page.
