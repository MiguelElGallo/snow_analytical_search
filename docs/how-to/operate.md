# Operate and update the demo

These instructions assume you have completed setup with `~/.config/snow-analytical-search/demo.toml`.

## Continue after AI access is enabled

Ingestion requires Snowflake AI access. If you are upgrading an earlier local
preparation, complete [the migration steps](#upgrade-from-retired-local-preparation)
before running these commands.

```bash
uv run sas check-ai
uv run sas ingest
uv run sas verify --corpus-only
uv run sas deploy
uv run sas verify
uv run sas verify-runtime
uv run sas evaluate
```

Stop at a failed command and inspect the evidence named in its output. The
evaluation is not accepted until its SQL trace and citations pass the
[rubric](../reference/evaluation.md).

## Pause or resume

```bash
uv run sas pause
uv run sas resume
```

`pause` suspends both indexing and serving, then suspends the warehouse. It also
works before Search has been created. `resume` resumes the configured search
service; the warehouse resumes on demand. It fails clearly when no service exists.

Search serving and warehouse compute have separate lifecycles. Suspending the
warehouse alone does not suspend a running search service. Storage continues to
exist while compute is paused. See [access and cost](../explanation/access-cost.md).

## Verify or repeat the same ingestion

```bash
uv run sas ingest
uv run sas verify --corpus-only
```

An unchanged native run should reuse all 13 documents and retain exactly the
first native run's page and chunk counts, without another parser or splitter call.
The integrity checks still contact GitHub and read staged originals back during
ingestion. `verify --corpus-only` checks source bytes, manifest, page/chunk
coverage, and stage names/sizes; it does not repeat the staged-byte downloads.

## Load a different upstream revision

Pause the current service **before** editing configuration. Then set
`source_commit` to a full 40-character commit SHA from the upstream repository.

```bash
uv run sas download
uv run sas ingest
uv run sas deploy
uv run sas verify
```

The new snapshot gets its own search service. Only after coverage checks does
deployment point the stable agent name at that service. Older snapshots, tables,
and services are retained; they are not automatically deleted. A command uses
only the snapshot in its current configuration, so keep an old config if you
need to operate an older service.

If the upstream folder gains an unsupported file type, ingestion stops. Add and
test its native ingestion support before claiming complete coverage of that revision.

## Native parsing and OCR

PDF parsing always uses `AI_PARSE_DOCUMENT` with `LAYOUT`, `page_split=true`,
and error details. Native failures stop ingestion and preserve their evidence.

With `native_ocr=true` (the default), native OCR supplements only pages containing
image references. It reuses the same native LAYOUT extraction, validates exact
physical-page alignment, and retains both raw responses and their query IDs.
This recovers printed chart labels without claiming unprinted numeric values.

Ingestion uses `SPLIT_TEXT_RECURSIVE_CHARACTER` for every PDF, JSON and
Markdown file. Splitting retains physical page boundaries, uses Markdown
structure for layout output and Markdown files, and uses ordinary separators for
JSON. The limit is 3,500 characters with up to 300 characters of overlap.

PDF parsing and OCR are AI operations. Reading JSON/Markdown source text and
Snowflake's recursive splitting are deterministic preparation steps.

## Upgrade from retired local preparation

The local PDF extractor, Python splitter and `extract-pdfs` command have been
removed. A configuration containing `pdf_parser="local"` is rejected before any
connection or paid AI call. Do not use that configuration with `sas pause`.

1. Preserve the old private configuration and evidence. Find the exact historical
   Search service name in its deployment report. Confirm it with
   `SHOW CORTEX SEARCH SERVICES IN SCHEMA <database>.APP`
   using its existing owner role. Check the account and object before changing it.
2. Suspend that specific service in Snowflake:

   ```sql
   ALTER CORTEX SEARCH SERVICE <database>.APP.<old_service> SUSPEND;
   SHOW CORTEX SEARCH SERVICES IN SCHEMA <database>.APP;
   ```

   Read back both `indexing_state` and `serving_state` as `SUSPENDED`. This retains
   the historical service and data; keep its private evidence for comparison.
3. Run `uv sync --locked`, then prepare a native private configuration from the
   current example, without the retired parser setting. Keep the old configuration
   as evidence; it is no longer an executable setup.
4. Run `uv run sas --config /path/to/native-demo.toml check-ai` with the native
   configuration. Only after it succeeds, run the ingestion sequence above with
   that same configuration. Native parsing uses its own snapshot and cache
   identity; historical extracted text is not imported.

Existing native configurations containing `pdf_parser="snowflake"` remain
compatible, but the field is no longer needed. Both native snapshot identities,
with and without supplemental OCR, are unchanged. An existing native deployment
can be verified and reused without parsing it again.

## Build the documentation

```bash
uv run zensical build --clean --strict
uv run zensical serve
```

The site is generated under ignored `site/`. These commands do not publish it.
