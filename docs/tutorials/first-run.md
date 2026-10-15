# Load your first corpus

You will download the sample documents, load their originals and page text into
Snowflake, and deploy a search agent when your account has AI access.

## Before you start

You need Python 3.11–3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and a working named connection in `~/.snowflake/connections.toml`. Use your
existing Snowflake CLI authentication. This project does not create credentials.

Setup requires `ACCOUNTADMIN`. Later commands select dedicated owner or runner
roles. Use a fresh resource prefix if the default names already belong to another
project. The commands create resources that consume Snowflake credits.

Self-service trials initially disable AI. An administrator can add a credit card
to enable it without upgrading or ending the trial. AI usage can consume the
remaining free balance. See [Snowflake's current trial rules](https://docs.snowflake.com/en/user-guide/admin-trial-account).

## 1. Prepare the project

From the repository root, run:

```bash
uv sync --locked --python 3.13
mkdir -p ~/.config/snow-analytical-search
cp demo.example.toml ~/.config/snow-analytical-search/demo.toml
```

Edit `~/.config/snow-analytical-search/demo.toml`. Set `connection` to your profile name and
`expected_account` to the value returned by this read-only check:

```bash
snow sql -c YOUR_CONNECTION -q 'SELECT CURRENT_ACCOUNT_NAME();'
```

Keep the pinned `source_commit` and `pdf_parser="snowflake"` for this tutorial.
The example placeholder for `expected_account` deliberately fails validation.

```bash
uv run sas preflight
```

Confirm the account and region. Preflight reports the existing cross-region
setting; it does not change it. If authentication stalls on macOS, use the
[Keychain troubleshooting guidance](../how-to/troubleshoot.md#macos-keychain).

## 2. Download the verified originals

```bash
uv run sas download
```

You should see 13 files downloaded, including seven PDFs. Together the PDFs have
273 physical pages. The six text files each use one logical page. The downloader
verifies the complete Git tree and every file's bytes. Native parsing happens
during ingestion after the originals are staged.

## 3. Create resources and load the documents

```bash
uv run sas setup
uv run sas check-ai
uv run sas ingest
uv run sas verify --corpus-only
```

Setup creates the dedicated database, warehouse, roles, schemas, stage, and
tables. Ingestion uploads each original, downloads it again to verify its hash,
then runs the native rebuild:

1. Parse all seven PDFs with `AI_PARSE_DOCUMENT` in `LAYOUT` mode and
   `page_split=true`, retaining each physical page separately. Pages with image
   references also receive native OCR to recover printed labels on the same page.
2. Chunk **all 13 files** — seven PDFs, five JSON files and one Markdown file —
   with `SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER`, processing one page at a
   time. Every chunk retains its source and page number: a one-based physical
   page for PDFs, or logical page 1 for each JSON/Markdown file.

The loader checks full text coverage and source provenance before committing
each document. Read [how the native rebuild preserves page references](../explanation/architecture.md#how-the-native-rebuild-preserves-page-references)
for the file-type handling, chunk limits and a concrete citation example.

For the pinned corpus, expect 13 documents, 279 pages and 13 staged files. The
chunk count depends on the parser/splitter; the current measured count belongs
in [capabilities and limits](../reference/capabilities.md). A parser error stops ingestion
and is preserved for inspection. There is no automatic local fallback.

Run `uv run sas ingest` once more. Its summary should report `processed: 0` and
`reused: 13`. Originals are checked again, but successful parsing and table
inserts are reused.

The `check-ai` prerequisite makes two small AI calls. If it fails with a trial
restriction, follow [trial access troubleshooting](../how-to/troubleshoot.md#trial-ai-access)
before ingestion. A successful response confirms those functions work; it does
not prove that Search or Agents work. A historical local-parser preparation run
must be rebuilt with the native setting before evaluating this pipeline.

## 4. Deploy the native search agent

```bash
uv run sas deploy
uv run sas verify
uv run sas verify-runtime
```

Deployment creates a multi-index Cortex Search service, checks all 13 sources,
then creates or updates the Cortex Agent. It reads back the agent configuration
and source-row count. `verify` also compares every indexed chunk's content and
provenance with the corpus. `verify-runtime` requests one Search of at most ten
passages, then a native SQL aggregate over that exact Search result. The same
query projects the actual user, role, secondary roles and warehouse. The verifier
checks query history and reads the cached result; it does not execute model SQL.

!!! warning "Live validation boundary"
    If `verify-runtime` reports that the native SQL tool is unavailable, stop
    analytical evaluation and retain the failed gate. This limitation was observed
    during validation; do not infer that deployment alone proves SQL execution. Individual `ask` calls can diagnose
    document Q&A, but do not establish successful SQL analysis.

## 5. Ask a question

```bash
uv run sas ask "What vacation tiers does Zava offer? Cite the source."
```

Inspect the answer and its citations. The company overview lists Standard,
Senior, and Executive tiers lasting 2, 4, and 6 weeks respectively. This is an
answer observed in the live diagnostic run and checked against the source.

After `verify-runtime` passes, run the broader evaluation. If it failed, keep
that result, use individual questions only for diagnostics, then pause:

```bash
uv run sas evaluate
```

Use the [evaluation rubric](../reference/evaluation.md) to assess evidence,
complete-corpus counts, ambiguity, and unsupported claims. The command requires
native search-plus-AI SQL evidence, but a human still needs to review answer quality.

## 6. Pause after the session

```bash
uv run sas pause
```

This suspends the current search service, if one exists, and the warehouse.
Stored originals and tables remain available for your next session.
