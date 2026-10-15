"""Independent read-only checks of native query results and corpus coverage."""

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .config import Config
from .db import Database, secondary_roles_disabled

PROVENANCE_COLUMNS = (
    "CHUNK_ID",
    "DOC_ID",
    "SOURCE_PATH",
    "FILE_TYPE",
    "KIND",
    "PAGE_NUMBER",
    "SNAPSHOT_ID",
    "SOURCE_COMMIT",
    "SHA256",
    "SOURCE_URL",
    "RELATIVE_PATH",
    "CHUNK",
)
CONTEXT_SELECT = (
    "SELECT CURRENT_USER() AS USER_NAME, CURRENT_ROLE() AS ROLE_NAME, "
    "CURRENT_SECONDARY_ROLES() AS SECONDARY_ROLES, CURRENT_WAREHOUSE() AS WAREHOUSE_NAME, "
    "COUNT(*) AS PASSAGES, COUNT(DISTINCT DOC_ID) AS DOCUMENTS "
    "FROM TABLE(RESULT_SCAN('{query_id}'))"
)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def canonical_sql(sql: str) -> str:
    # Preserve literals and case: these are server-returned copies of the same SQL.
    return sql.strip().rstrip(";").strip()


def sql_lineage(sql: str) -> tuple[set[str], bool]:
    """Recognize actual calls, ignoring comments and string contents.

    This is deliberately a narrow evidence check, not a full SQL data-flow proof.
    An AI call must reference the configured CHUNK text column in its arguments.
    """
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(sql):
        if sql[i].isspace():
            i += 1
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = len(sql) if end < 0 else end + 1
        elif sql.startswith("/*", i):
            depth, i = 1, i + 2
            while i < len(sql) and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unterminated SQL comment in native evidence")
        elif sql.startswith("$$", i):
            end = sql.find("$$", i + 2)
            if end < 0:
                raise ValueError("Unterminated SQL string in native evidence")
            tokens.append(("literal", sql[i + 2 : end]))
            i = end + 2
        elif sql[i] in "'\"":
            quote, value, i = sql[i], "", i + 1
            while i < len(sql):
                if sql[i] == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        value, i = value + quote, i + 2
                    else:
                        i += 1
                        break
                elif sql[i] == "\\" and quote == "'" and i + 1 < len(sql):
                    value, i = value + sql[i + 1], i + 2
                else:
                    value, i = value + sql[i], i + 1
            else:
                raise ValueError("Unterminated SQL quoted value in native evidence")
            tokens.append(("literal" if quote == "'" else "word", value))
        elif match := re.match(r"[A-Za-z_][A-Za-z_0-9$]*", sql[i:]):
            tokens.append(("word", match[0].upper()))
            i += len(match[0])
        else:
            tokens.append(("symbol", sql[i]))
            i += 1
    parents: set[str] = set()
    uses_chunk_ai = False
    for index, (kind, name) in enumerate(tokens):
        if kind != "word" or tokens[index + 1 : index + 2] != [("symbol", "(")]:
            continue
        if name == "RESULT_SCAN" and tokens[index + 3 : index + 4] == [("symbol", ")")]:
            if tokens[index + 2][0] == "literal":
                parents.add(tokens[index + 2][1])
        if name in {"AI_FILTER", "AI_EXTRACT", "AI_AGG"}:
            depth, argument_words = 1, set()
            for token_kind, value in tokens[index + 2 :]:
                if (token_kind, value) == ("symbol", "("):
                    depth += 1
                elif (token_kind, value) == ("symbol", ")"):
                    depth -= 1
                    if not depth:
                        break
                elif token_kind == "word":
                    argument_words.add(value)
            uses_chunk_ai |= not depth and "CHUNK" in argument_words
    return parents, uses_chunk_ai


def chunk_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[column]) for column in PROVENANCE_COLUMNS)


def verify_index(db: Database, config: Config) -> dict[str, Any]:
    """OWNER reconciles exact indexed content; no extra RUNNER grants are required."""
    columns = ", ".join(PROVENANCE_COLUMNS)
    expected = db.run(
        f"SELECT {columns} FROM {config.prefix}.CORPUS.CHUNKS WHERE SNAPSHOT_ID=%s",
        (config.snapshot,),
    )
    actual = db.run(
        f"SELECT {columns} FROM TABLE(CORTEX_SEARCH_DATA_SCAN(SERVICE_NAME => %s))",
        (config.service,),
    )
    expected_keys, actual_keys = {chunk_key(r) for r in expected}, {chunk_key(r) for r in actual}
    if (
        not expected
        or len(expected_keys) != len(expected)
        or len(actual_keys) != len(actual)
        or len({r["CHUNK_ID"] for r in actual}) != len(actual)
        or actual_keys != expected_keys
    ):
        raise ValueError("Indexed chunks or provenance differ from the configured corpus")
    return {
        "status": "verified",
        "chunks": len(actual),
        "query_id": db.query_id,
        "content_sha256": fingerprint(sorted(actual_keys)),
    }


def _timestamp(value: Any) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Query evidence must include timezone-aware timestamps")
    return result


def verify_query(
    db: Database, config: Config, report: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """Read the cached result, never execute SQL supplied by the model."""
    query_id, sql = payload.get("query_id"), payload.get("sql")
    if not isinstance(query_id, str) or not isinstance(sql, str) or not sql.strip():
        raise ValueError("Native query evidence lacks a query ID or SQL text")
    rows = db.run(
        "SELECT QUERY_ID, USER_NAME, ROLE_NAME, WAREHOUSE_NAME, EXECUTION_STATUS, "
        "QUERY_TEXT, START_TIME, END_TIME "
        f"FROM TABLE({config.prefix}.INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER("
        "RESULT_LIMIT=>1000)) WHERE QUERY_ID=%s",
        (query_id,),
    )
    if len(rows) != 1:
        raise ValueError("Native query is absent or ambiguous in same-user query history")
    row = rows[0]
    if (
        row["QUERY_ID"] != query_id
        or row["USER_NAME"] != db.identity["USER_NAME"]
        or row["ROLE_NAME"] != config.runner
        or row["WAREHOUSE_NAME"] != config.warehouse
        or row["EXECUTION_STATUS"] != "SUCCESS"
        or canonical_sql(row["QUERY_TEXT"]) != canonical_sql(sql)
        or not (
            _timestamp(report["created_at"])
            <= _timestamp(row["START_TIME"])
            <= _timestamp(row["END_TIME"])
            <= _timestamp(report["completed_at"])
        )
    ):
        raise ValueError("Native query history does not confirm this run's SQL and context")
    result = db.run("SELECT * FROM TABLE(RESULT_SCAN(%s))", (query_id,))
    return {"query_id": query_id, "sql": sql, "history": row, "rows": result}


def audit_run(db: Database, config: Config, report: dict[str, Any]) -> dict[str, Any]:
    """Verify each run independently; a previous context probe cannot certify it."""
    if report.get("snapshot_id") != config.snapshot or report.get("search_binding") != {
        "tool": "corpus_search",
        "service": config.service,
    }:
        raise ValueError("Run evidence does not match the configured Search snapshot")
    corpus = db.run(
        f"SELECT {', '.join(PROVENANCE_COLUMNS)} FROM {config.prefix}.CORPUS.CHUNKS "
        "WHERE SNAPSHOT_ID=%s",
        (config.snapshot,),
    )
    expected = {r["CHUNK_ID"]: chunk_key(r) for r in corpus}
    documents = db.run(
        f"SELECT DOC_ID, PAGE_COUNT FROM {config.prefix}.CORPUS.DOCUMENTS WHERE SNAPSHOT_ID=%s",
        (config.snapshot,),
    )
    page_counts = {r["DOC_ID"]: r["PAGE_COUNT"] for r in documents}
    searches, sql_results = [], []
    reachable: set[str] = set()
    candidate_ids: set[str] = set()
    for payload in report["persisted_search_results"]:
        checked = verify_query(db, config, report, payload)
        for row in checked["rows"]:
            if expected.get(row.get("CHUNK_ID")) != chunk_key(row):
                raise ValueError("Search result contains unknown or stale corpus content")
            candidate_ids.add(row["CHUNK_ID"])
        reachable.add(checked["query_id"])
        searches.append(checked)
    analytical = []
    for tool in report["sql_results"]:
        for content in tool.get("content", []):
            payload = content.get("json")
            if not isinstance(payload, dict) or not payload.get("sql"):
                continue
            checked = verify_query(db, config, report, payload)
            parents, uses_chunk_ai = sql_lineage(checked["sql"])
            checked["search_lineage_verified"] = bool(parents) and parents <= reachable
            if checked["search_lineage_verified"]:
                reachable.add(checked["query_id"])
                if uses_chunk_ai:
                    analytical.append(checked["query_id"])
            sql_results.append(checked)
    eligible = {r["CHUNK_ID"] for r in corpus if r["KIND"] != "query_example"}
    return {
        "search_queries": searches,
        "sql_queries": sql_results,
        "analytical_query_ids": analytical,
        "secondary_roles": "unverified_for_this_run",
        "candidate_scope": "persisted_search_results",
        "candidate_chunk_ids": sorted(candidate_ids),
        "eligible_chunks": len(eligible),
        "eligible_candidate_chunks": len(candidate_ids & eligible),
        "complete_candidate_coverage": bool(eligible) and eligible <= candidate_ids,
        "requires_sql_semantics_review": True,
        "citations": verify_citations(config, report, corpus, page_counts),
    }


def verify_citations(
    config: Config,
    report: dict[str, Any],
    corpus: list[dict[str, Any]],
    page_counts: dict[str, int],
) -> list[dict[str, Any]]:
    """Resolve citation identity and physical page; claim support still needs review."""
    by_id = {row["CHUNK_ID"]: row for row in corpus}
    checked = []
    for annotation in report.get("annotations", []):
        row = by_id.get(annotation.get("doc_id"))
        index = annotation.get("index")
        if (
            row is None
            or row["SNAPSHOT_ID"] != config.snapshot
            or row["SOURCE_COMMIT"] != config.source_commit
            or annotation.get("type") != "cortex_search_citation"
            or annotation.get("relative_path") != row["RELATIVE_PATH"]
            or annotation.get("stage_path") != "@" + config.stage
            or annotation.get("doc_title") != row["SOURCE_PATH"].rsplit("/", 1)[-1]
            or type(index) is not int
            or not 0 <= index <= len(report["answer"])
            or not 1 <= int(row["PAGE_NUMBER"]) <= page_counts.get(row["DOC_ID"], 0)
        ):
            raise ValueError("Citation identity, source version, or answer offset is invalid")
        checked.append(
            {
                "chunk_id": row["CHUNK_ID"],
                "source_path": row["SOURCE_PATH"],
                "physical_page": row["PAGE_NUMBER"],
                "index": index,
                "claim_support": "requires_review",
            }
        )
    return checked


def verify_probe(config: Config, audit: dict[str, Any], user: str) -> dict[str, Any]:
    searches = audit["search_queries"]
    if len(searches) != 1 or not 1 <= len(searches[0]["rows"]) <= 10:
        raise ValueError("Runtime probe requires one nonempty bounded Search result")
    expected_sql = CONTEXT_SELECT.format(query_id=searches[0]["query_id"])
    matches = [q for q in audit["sql_queries"] if canonical_sql(q["sql"]) == expected_sql]
    if len(matches) != 1 or len(matches[0]["rows"]) != 1:
        raise ValueError("No verified native SQL context aggregate over the same Search result")
    row = matches[0]["rows"][0]
    if (
        row.get("USER_NAME") != user
        or row.get("ROLE_NAME") != config.runner
        or row.get("WAREHOUSE_NAME") != config.warehouse
        or not secondary_roles_disabled(row.get("SECONDARY_ROLES"))
        or int(row.get("PASSAGES", -1)) != len(searches[0]["rows"])
        or int(row.get("DOCUMENTS", -1)) != len({r["DOC_ID"] for r in searches[0]["rows"]})
    ):
        raise ValueError("Native context aggregate has unexpected context or counts")
    return {"query_id": matches[0]["query_id"], "context": row}


def verify_inventory(audit: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    expected = {(e["doc_id"], e["path"], e["file_type"]) for e in entries}
    for query in audit["sql_queries"]:
        if not query["search_lineage_verified"]:
            continue
        rows = query["rows"]
        if rows and all({"DOC_ID", "SOURCE_PATH", "FILE_TYPE"} <= r.keys() for r in rows):
            actual = {(r["DOC_ID"], r["SOURCE_PATH"], r["FILE_TYPE"]) for r in rows}
            if len(rows) == len(expected) and actual == expected:
                return
    raise ValueError("No native inventory result matches the exact verified source-file set")
