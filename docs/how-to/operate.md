# Operate and update the demo

These instructions assume you have completed setup with `~/.config/snow-analytical-search/demo.toml`.

## Continue after AI access is enabled

If the corpus was prepared with `pdf_parser="local"`, rebuild it natively. First
pause its service using the old configuration and retain that configuration for
historical service control. Then set `pdf_parser="snowflake"`.

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
test an extractor before claiming complete coverage of that revision.

## Parser choice and historical local preparation

Set `pdf_parser="snowflake"` only on an account where `AI_PARSE_DOCUMENT` works.
Pause the old service first. Skip `extract-pdfs`, then run `ingest`, `deploy`,
and `verify`. Native parsing uses `LAYOUT`, `page_split=true`, and error details.
Changing parser produces a different snapshot and cache identity.

With `native_ocr=true` (the default), native OCR supplements only pages containing
image references. It reuses the same native LAYOUT extraction, validates exact
physical-page alignment, and retains both raw responses and their query IDs.
This recovers printed chart labels without claiming unprinted numeric values.

Native mode also uses `SPLIT_TEXT_RECURSIVE_CHARACTER` for every PDF, JSON and
Markdown file. Splitting retains physical page boundaries, uses Markdown
structure for layout output and Markdown files, and uses ordinary separators for
JSON. The limit is 3,500 characters with up to 300 characters of overlap.

The explicit `local` mode remains available to reproduce historical preparation:
run `extract-pdfs` before `ingest`. It uses pypdf and the old Python splitter; it
is not the native pipeline and cannot be used as its acceptance evidence.

## Build the documentation

```bash
uv run zensical build --clean --strict
uv run zensical serve
```

The site is generated under ignored `site/`. These commands do not publish it.
