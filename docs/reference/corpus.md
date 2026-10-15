# Corpus and tables

Source: [Azure sample data at the pinned commit](https://github.com/Azure-Samples/azure-search-openai-demo/tree/558ffd397eddcfe4da5c85ebc285796b367eb9b2/data).

Commit: `558ffd397eddcfe4da5c85ebc285796b367eb9b2`.
Default native snapshot: `8f805241c0e87c37f920ab29` (LAYOUT + filtered OCR + native splitter).
See [capabilities and limits](capabilities.md) for content checks.
See [the ingestion diagrams](../explanation/ingestion.md) for how each file type
becomes pages and chunks.

## Complete inventory

Paths are relative to the upstream `data/` directory. The loader includes nested
directories without flattening filenames.

| Source path | Type | Pages |
| --- | --- | ---: |
| `Benefit_Options.pdf` | PDF | 4 |
| `Json_Examples/2189.json` | JSON | 1 |
| `Json_Examples/2190.json` | JSON | 1 |
| `Json_Examples/2191.json` | JSON | 1 |
| `Json_Examples/2192.json` | JSON | 1 |
| `Json_Examples/query.json` | JSON | 1 |
| `Multimodal_Examples/Financial Market Analysis Report 2023.pdf` | PDF | 10 |
| `Northwind_Health_Plus_Benefits_Details.pdf` | PDF | 109 |
| `Northwind_Standard_Benefits_Details.pdf` | PDF | 104 |
| `PerksPlus.pdf` | PDF | 4 |
| `Zava_Company_Overview.md` | Markdown | 1 |
| `employee_handbook.pdf` | PDF | 11 |
| `role_library.pdf` | PDF | 31 |
| **Total** | **13 documents** | **279** |

PDF page numbers are one-based physical pages, including cover and disclaimer
pages. JSON and Markdown use one logical page. The measured native run has **281 chunks**.
Recheck the count after changing parser options or the source version.

`query.json` is retained as `KIND=query_example`. Its example queries are source
text: the loader never executes them, and the agent is instructed to exclude
them from policy evidence. The other JSON files have `KIND=json_example`.

## Tables

All three corpus tables use `SNAPSHOT_ID` to separate versions. SQL comparisons
must filter on it; older snapshots remain stored.

| Table | One row per | Fields |
| --- | --- | --- |
| `RAW.PARSE_CACHE` | Cached PDF extraction | `SHA256`, `PIPELINE_VERSION`, `RESULT`, `PARSE_QUERY_ID`, `CREATED_AT` |
| `CORPUS.DOCUMENTS` | Original file in a snapshot | Source path/URL/commit/hash, type, kind, byte size, page count, chunk count, stage path |
| `CORPUS.PAGES` | Physical or logical page | Snapshot, document ID, page number, content |
| `CORPUS.CHUNKS` | Search passage | Snapshot, chunk/document IDs, content, filename, source provenance, page number, stage path |

`DOC_ID` hashes the source path. `CHUNK_ID` hashes the snapshot, document ID,
physical page, and within-page chunk index. Neither identifier is an answer or a
semantic document classification.

Native envelopes and chunk evidence retain actual Snowflake query IDs. Composite
LAYOUT-plus-OCR envelopes have no single parse query ID; their `inputs` preserve
both original query IDs, artifact hashes and source-bound provenance.
Snapshot identity also includes native chunking version/options. Cached output
must match the source hash and native pipeline identity before reuse.

## Independent inventory query

For the active native snapshot, run as the project runner:

```sql
SELECT FILE_TYPE, COUNT(DISTINCT DOC_ID) AS DOCUMENTS
FROM SNOW_ANALYTICAL_SEARCH.CORPUS.DOCUMENTS
WHERE SNAPSHOT_ID = '8f805241c0e87c37f920ab29'
GROUP BY FILE_TYPE
ORDER BY FILE_TYPE;
```

Expected result: `json=5`, `md=1`, `pdf=7`. Counting chunks would return 281 and
would answer a different question.
