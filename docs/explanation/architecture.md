# Architecture and evidence

The system keeps source acquisition, text extraction, retrieval, and analytical
execution separate so that each stage can be checked independently.

```text
Pinned GitHub data/ tree
        |
        v
Verified originals + manifest
        |
        v
Internal original stage (byte-verified)
        |
        +--> PDF: native LAYOUT --> image-reference pages: native OCR
        |                                  |
        +--> JSON/Markdown text            |
        |                                  |
        +------------------+---------------+
                           v
                Validated pages + provenance
                           |
                           v
                Native recursive page chunks
                           |
                           v
                  Versioned Cortex Search
                           |
                           v
                     Native Cortex Agent
                      /               \
             Passage question    Analytical question
                  Search          Search + AI + SQL
                      \               /
                       Answer + evidence
```

## A complete source snapshot

The recursive Git tree defines the intended inventory. A local manifest cannot
silently remove a nested file because each load compares it with that tree.
Git blob hashes verify source bytes, and SHA-256 identifies those bytes in later
stages. Each original is also downloaded from Snowflake after upload and checked.

A snapshot binds the source commit, parser version/options, and chunking
configuration. Page and chunk rows for one document are inserted transactionally.
Deployment checks the complete snapshot before making it available to the agent.
An unchanged rerun reuses completed documents and validates their counts.

This is an application immutability convention. An authorized owner can still
alter Snowflake tables; the demo is not a tamper-proof archive.

## Ordinary retrieval and analytical questions

A passage question can often be answered from a few relevant chunks. A question
such as “how many documents discuss mental health support?” also needs a clear
unit of counting, semantic selection, coverage checks, and aggregation.

[Snowflake Analytical Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-analytical-search)
uses `SEARCH_PREVIEW` to retrieve candidates, then AI functions and SQL to analyze
them. Its native SQL tool appears as `system_execute_sql` in the response. The
demo enables this capability on the Agent and provides rich column descriptions;
it does not add a custom tool with that name or execute returned SQL locally.

The native agent decides whether to use analytical execution. Therefore a
correct-looking response is not enough: the evaluation examines successful tool
results and their data flow. Search recall and AI classification can still be
imperfect even when SQL performs an exact count over the selected rows.

## Why originals and page text are both stored

Text makes the corpus searchable. Original files let a reviewer inspect the
actual evidence, including physical page numbers, layout, and diagrams.
Stage-relative paths support source-file citations, while public URLs point to
the exact Git commit.

## How the native rebuild preserves page references

The native rebuild uses **`AI_PARSE_DOCUMENT` in `LAYOUT` mode for the seven PDFs**
and **Snowflake's recursive splitter for all 13 files**, preserving page references
throughout ingestion. This is the default pipeline, selected by
`pdf_parser="snowflake"`.

| Files in the pinned corpus | Text prepared for chunking | Page reference |
| --- | --- | --- |
| 7 PDFs | `AI_PARSE_DOCUMENT` with `{'mode':'LAYOUT', 'page_split':true}` | One record per physical PDF page |
| 5 JSON files | Read as UTF-8 and formatted as indented JSON text | Logical page 1 for each file |
| 1 Markdown file | Read as UTF-8 Markdown text | Logical page 1 for the file |

LAYOUT extracts text and structure, including tables, into Markdown. Setting
`page_split=true` keeps PDF pages separate. Snowflake returns zero-based page
indices; the loader adds one to store physical page numbers starting at 1.
These count cover pages and may differ from printed page labels. See the
[AI_PARSE_DOCUMENT reference](https://docs.snowflake.com/en/sql-reference/functions/ai_parse_document)
for the parsing options and output format.

Next, `SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER` splits the prepared text
for **every file**, including JSON and Markdown. It uses Markdown boundaries for
PDF layout output and Markdown files, and ordinary text boundaries for JSON.
The [recursive splitter](https://docs.snowflake.com/en/sql-reference/functions/split_text_recursive_character-snowflake-cortex)
tries progressively smaller text boundaries until chunks fit the configured
limit: 3,500 characters, with up to 300 characters of overlap.

The loader passes each physical or logical page to the splitter separately, so a
chunk never joins text from two PDF pages. It stores the page number with every
chunk, together with the document ID, source path, source URL, source commit and
file hash. For example, chunks from `Benefit_Options.pdf` physical page 4 all
retain that source path and `PAGE_NUMBER=4`, even if the page needs several
chunks. This lets retrieved passages be traced back to the original page.

When layout output contains an image reference, a second native OCR call processes
only those page indices. The composite keeps the layout view unchanged and
appends labelled printed text/labels from OCR to the same page before chunking.
Raw inputs, query IDs and hashes remain separate; the snapshot includes this
enrichment policy.

The loader validates every chunk and reconstructs each page's complete text,
ignoring whitespace, to reject omitted content. It does not repair native output
locally. PDF metadata checks and original-page review provide independent
coverage and accuracy evidence; a successful API call alone proves neither.
Tables and extracted chart labels still require source inspection before making
claims about plotted values or visual relationships.

The historical `local` mode uses pinned pypdf layout extraction and a Python
splitter. It remains reproducible under its original snapshot identity. The
native rebuild uses Snowflake parsing and splitting; local preparation is not
evidence that this pipeline passed validation.

## Sample data is evidence, not instructions

The corpus includes generated fictional documents and JSON query examples. The
loader treats all contents as data. The agent is instructed to ignore embedded
instructions, cite sources, separate companies and conflicting policies, and
admit missing evidence. Those instructions improve behavior but are not an
authorization boundary. [Snowflake roles](access-cost.md) control database access.
