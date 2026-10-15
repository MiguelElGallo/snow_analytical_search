"""Provision isolated resources and load immutable, complete corpus snapshots."""

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from .config import CHUNK_OVERLAP, CHUNK_SIZE, Config, identifier, literal
from .db import Database
from .extraction import (
    checked_chunks,
    checked_parse,
    chunk_id,
    chunks,
    decode,
    parse_path,
    pdf_pages,
    provenance,
    text_pages,
)
from .source import check_bytes, read_manifest, write_json

MARKER = "Managed by snow-analytical-search showcase"


def _check_existing(db: Database, object_type: str, name: str) -> bool:
    rows = db.run(f"SHOW {object_type} LIKE {literal(name)}")
    matching = [row for row in rows if row.get("name") == name]
    if matching and matching[0].get("comment") != MARKER:
        raise ValueError(f"Refusing to adopt unrelated existing {object_type}: {name}")
    return bool(matching)


def setup(config: Config) -> dict[str, Any]:
    with Database(config, "ACCOUNTADMIN", bootstrap=True) as db:
        for role in (config.owner, config.runner):
            _check_existing(db, "ROLES", role)
            db.run(f"CREATE ROLE IF NOT EXISTS {role} COMMENT = {literal(MARKER)}")
            db.run(f"GRANT ROLE {role} TO USER {identifier(db.identity['USER_NAME'])}")
        _check_existing(db, "WAREHOUSES", config.warehouse)
        db.run(
            f"CREATE WAREHOUSE IF NOT EXISTS {config.warehouse} WAREHOUSE_SIZE='XSMALL' "
            f"AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE "
            f"COMMENT={literal(MARKER)}"
        )
        _check_existing(db, "DATABASES", config.prefix)
        db.run(f"CREATE DATABASE IF NOT EXISTS {config.prefix} COMMENT={literal(MARKER)}")
        db.run(f"GRANT USAGE, CREATE SCHEMA ON DATABASE {config.prefix} TO ROLE {config.owner}")
        for role in (config.owner, config.runner):
            db.run(f"GRANT USAGE ON WAREHOUSE {config.warehouse} TO ROLE {role}")
            db.run(f"GRANT USAGE ON DATABASE {config.prefix} TO ROLE {role}")
            db.run(f"GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE {role}")
        db.run(f"GRANT OPERATE ON WAREHOUSE {config.warehouse} TO ROLE {config.owner}")
    with Database(config, config.owner, bootstrap=True) as db:
        db.run(f"USE WAREHOUSE {config.warehouse}")
        for schema in ("RAW", "CORPUS", "APP", "SCRATCH"):
            db.run(f"CREATE SCHEMA IF NOT EXISTS {config.prefix}.{schema}")
            db.run(f"GRANT USAGE ON SCHEMA {config.prefix}.{schema} TO ROLE {config.runner}")
        db.run(
            f"CREATE STAGE IF NOT EXISTS {config.stage} "
            "ENCRYPTION=(TYPE='SNOWFLAKE_SSE') DIRECTORY=(ENABLE=TRUE)"
        )
        db.run(f"GRANT READ ON STAGE {config.stage} TO ROLE {config.runner}")
        db.run(f"GRANT CREATE TABLE ON SCHEMA {config.prefix}.SCRATCH TO ROLE {config.runner}")
        db.run(f"""CREATE TABLE IF NOT EXISTS {config.prefix}.RAW.PARSE_CACHE (
            SHA256 VARCHAR, PIPELINE_VERSION VARCHAR, RESULT VARIANT,
            PARSE_QUERY_ID VARCHAR, CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""")
        db.run(f"""CREATE TABLE IF NOT EXISTS {config.prefix}.CORPUS.DOCUMENTS (
            SNAPSHOT_ID VARCHAR, DOC_ID VARCHAR, SOURCE_PATH VARCHAR, SOURCE_URL VARCHAR,
            FILE_TYPE VARCHAR, KIND VARCHAR, SOURCE_COMMIT VARCHAR, SHA256 VARCHAR,
            BYTE_SIZE NUMBER, PAGE_COUNT NUMBER, CHUNK_COUNT NUMBER, RELATIVE_PATH VARCHAR)""")
        db.run(f"""CREATE TABLE IF NOT EXISTS {config.prefix}.CORPUS.PAGES (
            SNAPSHOT_ID VARCHAR, DOC_ID VARCHAR, PAGE_NUMBER NUMBER, CONTENT VARCHAR)""")
        db.run(f"""CREATE TABLE IF NOT EXISTS {config.prefix}.CORPUS.CHUNKS (
            SNAPSHOT_ID VARCHAR, CHUNK_ID VARCHAR, DOC_ID VARCHAR, CHUNK VARCHAR,
            TITLE VARCHAR, SOURCE_PATH VARCHAR, SOURCE_URL VARCHAR, FILE_TYPE VARCHAR,
            KIND VARCHAR, PAGE_NUMBER NUMBER, SOURCE_COMMIT VARCHAR, SHA256 VARCHAR,
            RELATIVE_PATH VARCHAR) CHANGE_TRACKING=TRUE""")
        for table in ("DOCUMENTS", "PAGES", "CHUNKS"):
            db.run(f"GRANT SELECT ON TABLE {config.prefix}.CORPUS.{table} TO ROLE {config.runner}")
        return {"identity": db.identity, "database": config.prefix, "warehouse": config.warehouse}


def upload(db: Database, config: Config, entry: dict[str, Any]) -> None:
    path = config.corpus_dir / entry["path"]
    parent = PurePosixPath(entry["path"]).parent
    target = f"@{config.stage}/{config.source_commit}/{parent}"
    rows = db.run(
        f"PUT {literal('file://' + str(path))} {literal(target)} "
        "AUTO_COMPRESS=FALSE OVERWRITE=FALSE"
    )
    if not rows or any(row.get("status") not in {"UPLOADED", "SKIPPED"} for row in rows):
        raise ValueError(f"Stage upload failed: {entry['path']}")
    verify_staged_bytes(db, config, entry)


def verify_staged_bytes(db: Database, config: Config, entry: dict[str, Any]) -> None:
    """Read the uploaded original back; size and PUT=SKIPPED are insufficient evidence."""
    config.state_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="stage-check-", dir=config.state_dir) as temporary:
        remote = f"@{config.stage}/{config.source_commit}/{entry['path']}"
        db.run(f"GET {literal(remote)} {literal('file://' + temporary + '/')}")
        files = [path for path in Path(temporary).rglob("*") if path.is_file()]
        if len(files) != 1:
            raise ValueError(f"Expected one staged original for {entry['path']}")
        if check_bytes(files[0].read_bytes(), entry) != entry["sha256"]:
            raise ValueError(f"Staged original hash mismatch: {entry['path']}")


def extract(db: Database, config: Config, entry: dict[str, Any]) -> list[tuple[int, str]]:
    if entry["file_type"] != "pdf":
        return text_pages((config.corpus_dir / entry["path"]).read_bytes(), entry["file_type"])
    cache = db.run(
        f"SELECT RESULT FROM {config.prefix}.RAW.PARSE_CACHE "
        "WHERE SHA256=%s AND PIPELINE_VERSION=%s",
        (entry["sha256"], config.pipeline_identity),
    )
    if cache:
        if len(cache) != 1:
            raise ValueError(f"Duplicate PDF parse cache rows: {entry['path']}")
        result = decode(cache[0]["RESULT"])
        pages = checked_parse(result, config, entry)
        target = parse_path(config, entry)
        if target.exists():
            if json.loads(target.read_text()) != result:
                raise ValueError(f"Local and Snowflake parse evidence differ: {entry['path']}")
        else:
            write_json(target, result)
        return pages
    if config.pdf_parser == "local":
        target = parse_path(config, entry)
        if not target.exists():
            raise ValueError("Run extract-pdfs with the configured local parser before ingest")
        result = json.loads(target.read_text())
        parse_query_id = None
    elif config.native_ocr:
        result = enriched_native_parse(db, config, entry)
        parse_query_id = None  # Composite: actual query IDs are retained with both inputs.
        write_json(parse_path(config, entry), result)
    else:
        result = decode(
            db.scalar(
                "SELECT AI_PARSE_DOCUMENT(TO_FILE(%s, %s), "
                "{'mode':'LAYOUT', 'page_split':true}, TRUE)",
                (f"@{config.stage}", f"{config.source_commit}/{entry['path']}"),
            )
        )
        parse_query_id = db.query_id
        if not isinstance(result, dict):
            raise ValueError("Native parser did not return a JSON envelope")
        result["provenance"] = provenance(config, entry)
        result["parse_query_id"] = parse_query_id
        write_json(parse_path(config, entry), result)
    pages = checked_parse(result, config, entry)
    db.run(
        f"INSERT INTO {config.prefix}.RAW.PARSE_CACHE "
        "(SHA256, PIPELINE_VERSION, RESULT, PARSE_QUERY_ID) "
        "SELECT %s, %s, PARSE_JSON(%s), %s",
        (entry["sha256"], config.pipeline_identity, json.dumps(result), parse_query_id),
    )
    return pages


def enriched_native_parse(db: Database, config: Config, entry: dict[str, Any]) -> dict[str, Any]:
    # Reuse the unchanged native LAYOUT call under its original immutable identity.
    layout_config = replace(config, native_ocr=False)
    layout_pages = extract(db, layout_config, entry)
    layout_path = parse_path(layout_config, entry)
    layout_result = json.loads(layout_path.read_text())
    inputs = {
        "layout": {
            "path": str(layout_path),
            "sha256": hashlib.sha256(layout_path.read_bytes()).hexdigest(),
            "query_id": layout_result["parse_query_id"],
            "pipeline": layout_config.pipeline_identity,
        }
    }
    indices = [page - 1 for page, text in layout_pages if re.search(r"!\[[^\]]*\]\(", text)]
    ocr_pages: dict[int, str] = {}
    if indices:
        options = {"mode": "OCR", "page_filter": [{"start": i, "end": i + 1} for i in indices]}
        target = config.state_dir / "ocr" / config.snapshot / f"{entry['sha256']}.json"
        if target.exists():
            result = json.loads(target.read_text())
        else:
            result = decode(
                db.scalar(
                    "SELECT AI_PARSE_DOCUMENT(TO_FILE(%s,%s),PARSE_JSON(%s),TRUE)",
                    (
                        f"@{config.stage}",
                        f"{config.source_commit}/{entry['path']}",
                        json.dumps(options),
                    ),
                )
            )
            if not isinstance(result, dict):
                raise ValueError("Native OCR did not return a JSON envelope")
            result.update(
                provenance=provenance(config, entry), options=options, parse_query_id=db.query_id
            )
            write_json(target, result)
        if (
            result.get("provenance") != provenance(config, entry)
            or result.get("options") != options
        ):
            raise ValueError("Native OCR source or options mismatch")
        ocr_pages = dict(
            pdf_pages(result, expected_indices=indices, expected_count=len(layout_pages))
        )
        inputs["ocr"] = {
            "path": str(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "query_id": result["parse_query_id"],
            "pipeline": config.pipeline_identity,
        }
    return {
        "provenance": provenance(config, entry),
        "derivation": "native-layout-plus-image-page-ocr-v1",
        "inputs": inputs,
        "error": None,
        "metadata": {"pageCount": len(layout_pages)},
        "value": {
            "pages": [
                {
                    "index": page - 1,
                    "content": text
                    + (
                        "\n\n## Additional native OCR of this physical page\n"
                        "Printed text and labels only; plotted values and visual relationships "
                        "are not established by this extraction.\n\n" + ocr_pages[page]
                        if page in ocr_pages
                        else ""
                    ),
                }
                for page, text in layout_pages
            ]
        },
    }


def native_chunks(
    db: Database, config: Config, entry: dict[str, Any], pages: list[tuple[int, str]]
) -> list[tuple[int, int, str]]:
    format_name = "none" if entry["file_type"] == "json" else "markdown"
    sql = (
        "SELECT p.value[0]::NUMBER PAGE_NUMBER, c.index::NUMBER CHUNK_INDEX, "
        "c.value::VARCHAR CHUNK, TYPEOF(c.value) CHUNK_TYPE "
        "FROM TABLE(FLATTEN(INPUT=>PARSE_JSON(%s))) p, "
        "LATERAL FLATTEN(INPUT=>SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER("
        f"p.value[1]::VARCHAR, %s, {CHUNK_SIZE}, {CHUNK_OVERLAP}), OUTER=>TRUE) c "
        "ORDER BY PAGE_NUMBER, CHUNK_INDEX"
    )
    rows = db.run(sql, (json.dumps(pages), format_name))
    # Retain the unmodified native output even when a validation check fails.
    write_json(
        config.state_dir / "chunks" / config.snapshot / f"{entry['doc_id']}.json",
        {
            "snapshot_id": config.snapshot,
            "source_path": entry["path"],
            "provenance": provenance(config, entry),
            "query_id": db.query_id,
            "sql": sql,
            "format": format_name,
            "rows": rows,
        },
    )
    return checked_chunks(pages, rows)


def _insert_document(
    db: Database, config: Config, entry: dict[str, Any], pages: list[tuple[int, str]]
) -> int:
    parts = (
        native_chunks(db, config, entry, pages)
        if config.pdf_parser == "snowflake"
        else [
            (page, index, content)
            for page, text in pages
            for index, content in enumerate(chunks(text))
        ]
    )
    chunk_rows = []
    for page, index, content in parts:
        chunk_rows.append(
            [
                config.snapshot,
                chunk_id(config.snapshot, entry["doc_id"], page, index),
                entry["doc_id"],
                content,
                PurePosixPath(entry["path"]).name,
                entry["path"],
                entry["source_url"],
                entry["file_type"],
                entry["kind"],
                page,
                config.source_commit,
                entry["sha256"],
                f"{config.source_commit}/{entry['path']}",
            ]
        )
    if not chunk_rows:
        raise ValueError(f"No indexable content: {entry['path']}")
    db.run("BEGIN")
    try:
        for table in ("DOCUMENTS", "PAGES", "CHUNKS"):
            db.run(
                f"DELETE FROM {config.prefix}.CORPUS.{table} WHERE SNAPSHOT_ID=%s AND DOC_ID=%s",
                (config.snapshot, entry["doc_id"]),
            )
        db.run(
            f"INSERT INTO {config.prefix}.CORPUS.DOCUMENTS "
            "SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s",
            (
                config.snapshot,
                entry["doc_id"],
                entry["path"],
                entry["source_url"],
                entry["file_type"],
                entry["kind"],
                config.source_commit,
                entry["sha256"],
                entry["size"],
                len(pages),
                len(chunk_rows),
                f"{config.source_commit}/{entry['path']}",
            ),
        )
        db.run(
            f"INSERT INTO {config.prefix}.CORPUS.PAGES "
            "SELECT %s,%s,value[0]::NUMBER,value[1]::VARCHAR "
            "FROM TABLE(FLATTEN(INPUT=>PARSE_JSON(%s)))",
            (config.snapshot, entry["doc_id"], json.dumps(pages)),
        )
        columns = [f"value[{i}]::{('NUMBER' if i == 9 else 'VARCHAR')}" for i in range(13)]
        db.run(
            f"INSERT INTO {config.prefix}.CORPUS.CHUNKS SELECT {','.join(columns)} "
            "FROM TABLE(FLATTEN(INPUT=>PARSE_JSON(%s)))",
            (json.dumps(chunk_rows),),
        )
        db.run("COMMIT")
    except Exception:
        db.run("ROLLBACK")
        raise
    return len(chunk_rows)


def ingest(config: Config) -> dict[str, Any]:
    entries = read_manifest(config)
    processed, reused = 0, 0
    with Database(config, config.owner) as db:
        for entry in entries:
            upload(db, config, entry)
            existing = db.run(
                f"SELECT SHA256 FROM {config.prefix}.CORPUS.DOCUMENTS "
                "WHERE SNAPSHOT_ID=%s AND DOC_ID=%s",
                (config.snapshot, entry["doc_id"]),
            )
            if existing:
                if len(existing) != 1 or existing[0]["SHA256"] != entry["sha256"]:
                    raise ValueError("Snapshot collision or duplicate manifest rows")
                reused += 1
                print(f"Reused {entry['path']}", flush=True)
                continue
            pages = extract(db, config, entry)
            count = _insert_document(db, config, entry, pages)
            processed += 1
            print(f"Loaded {entry['path']}: {len(pages)} pages, {count} chunks", flush=True)
        report = verify_corpus(db, config, entries)
        report.update(processed=processed, reused=reused)
    write_json(config.state_dir / "ingestion.json", report)
    write_json(config.state_dir / "snapshots" / config.snapshot / "ingestion.json", report)
    return report


def verify_corpus(db: Database, config: Config, entries: list[dict[str, Any]]) -> dict[str, Any]:
    docs = db.run(
        f"SELECT * FROM {config.prefix}.CORPUS.DOCUMENTS WHERE SNAPSHOT_ID=%s ORDER BY SOURCE_PATH",
        (config.snapshot,),
    )
    expected = {(e["path"], e["sha256"], e["doc_id"]) for e in entries}
    actual = {(d["SOURCE_PATH"], d["SHA256"], d["DOC_ID"]) for d in docs}
    if len(docs) != len(entries) or expected != actual:
        raise ValueError("Source inventory and Snowflake manifest do not match")
    counts = db.run(
        f"SELECT DOC_ID, COUNT(*) N, COUNT(DISTINCT CHUNK_ID) DISTINCT_N "
        f"FROM {config.prefix}.CORPUS.CHUNKS WHERE SNAPSHOT_ID=%s GROUP BY DOC_ID",
        (config.snapshot,),
    )
    by_doc = {row["DOC_ID"]: row for row in counts}
    if set(by_doc) != {d["DOC_ID"] for d in docs}:
        raise ValueError("Chunk document set differs from the source inventory")
    page_rows = db.run(
        f"SELECT DOC_ID, PAGE_NUMBER, CONTENT FROM {config.prefix}.CORPUS.PAGES "
        "WHERE SNAPSHOT_ID=%s",
        (config.snapshot,),
    )
    pages_by_doc: dict[str, list[int]] = {}
    for page in page_rows:
        if not isinstance(page["CONTENT"], str) or not page["CONTENT"].strip():
            raise ValueError("Stored page has no text")
        pages_by_doc.setdefault(page["DOC_ID"], []).append(page["PAGE_NUMBER"])
    if set(pages_by_doc) != {d["DOC_ID"] for d in docs}:
        raise ValueError("Page document set differs from the source inventory")
    for doc in docs:
        row = by_doc.get(doc["DOC_ID"], {})
        if row.get("N") != doc["CHUNK_COUNT"] or row.get("DISTINCT_N") != doc["CHUNK_COUNT"]:
            raise ValueError(f"Missing or duplicate chunks: {doc['SOURCE_PATH']}")
        if sorted(pages_by_doc[doc["DOC_ID"]]) != list(range(1, doc["PAGE_COUNT"] + 1)):
            raise ValueError(f"Missing or duplicate stored pages: {doc['SOURCE_PATH']}")
    staged = db.run(f"LIST '@{config.stage}/{config.source_commit}/data/'")
    if len(staged) != len(entries):
        raise ValueError("Staged file count differs from the pinned source inventory")
    for entry in entries:
        suffix = f"/{config.source_commit}/{entry['path']}"
        matches = [r for r in staged if r["name"].endswith(suffix)]
        if len(matches) != 1 or matches[0]["size"] != entry["size"]:
            raise ValueError(f"Missing or wrong-size staged original: {entry['path']}")
    return {
        "snapshot_id": config.snapshot,
        "source_commit": config.source_commit,
        "parser": config.parser_identity,
        "pipeline": config.pipeline_identity,
        "documents": len(docs),
        "pages": sum(d["PAGE_COUNT"] for d in docs),
        "chunks": sum(d["CHUNK_COUNT"] for d in docs),
        "staged_files": len(staged),
        "files": docs,
        "identity": db.identity,
    }
