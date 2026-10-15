import json
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

import pytest

from snow_analytical_search.agent import evaluate, verify_runtime
from snow_analytical_search.config import Config
from snow_analytical_search.db import Database, secondary_roles_disabled
from snow_analytical_search.evidence import (
    CONTEXT_SELECT,
    PROVENANCE_COLUMNS,
    audit_run,
    verify_citations,
    verify_index,
    verify_inventory,
    verify_probe,
    verify_query,
)


@pytest.fixture
def evidence(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    row: dict[str, Any] = dict.fromkeys(PROVENANCE_COLUMNS, "example")
    row.update(
        CHUNK_ID="chunk",
        DOC_ID="doc",
        SOURCE_PATH="data/example.md",
        FILE_TYPE="md",
        SNAPSHOT_ID=config.snapshot,
        SOURCE_COMMIT=config.source_commit,
        PAGE_NUMBER=1,
        KIND="document",
        RELATIVE_PATH=config.source_commit + "/data/example.md",
    )
    sql = CONTEXT_SELECT.format(query_id="search-query")
    payload = {
        "query_id": "native-query",
        "sql": sql,
        "result_set": {"data": [["USER", config.runner]]},
    }  # No rowType.
    report: dict[str, Any] = {
        "created_at": "2026-10-15T08:00:00+00:00",
        "completed_at": "2026-10-15T08:01:00+00:00",
        "snapshot_id": config.snapshot,
        "search_binding": {"tool": "corpus_search", "service": config.service},
        "persisted_search_results": [
            {"query_id": "search-query", "sql": "SELECT SEARCH_PREVIEW(?, ?)"}
        ],
        "sql_results": [{"content": [{"json": payload}]}],
        "annotations": [],
    }
    context = {
        "USER_NAME": "USER",
        "ROLE_NAME": config.runner,
        "WAREHOUSE_NAME": config.warehouse,
        "SECONDARY_ROLES": '{"roles":"","value":""}',
        "PASSAGES": 1,
        "DOCUMENTS": 1,
    }
    history = {
        "QUERY_ID": "native-query",
        "USER_NAME": "USER",
        "ROLE_NAME": config.runner,
        "WAREHOUSE_NAME": config.warehouse,
        "EXECUTION_STATUS": "SUCCESS",
        "QUERY_TEXT": sql,
        "START_TIME": "2026-10-15T08:00:15+00:00",
        "END_TIME": "2026-10-15T08:00:20+00:00",
    }
    db = MagicMock(spec=Database)
    db.identity = {"USER_NAME": "USER"}
    db.query_id = "audit-query"

    def run(statement, params=None):
        if ".CORPUS.DOCUMENTS" in statement:
            return [{"DOC_ID": "doc", "PAGE_COUNT": 1}]
        if ".CORPUS.CHUNKS" in statement:
            return [row]
        if "QUERY_HISTORY" in statement:
            if params == ("search-query",):
                return [
                    {
                        **history,
                        "QUERY_ID": "search-query",
                        "QUERY_TEXT": report["persisted_search_results"][0]["sql"],
                    }
                ]
            return [history]
        if "RESULT_SCAN" in statement:
            return [row] if params == ("search-query",) else [context]
        raise AssertionError(statement)

    db.run.side_effect = run
    return config, db, report, payload, history, context, row


@pytest.mark.parametrize(
    "value",
    [
        None,
        "{}",
        "null",
        "[]",
        "{",
        '{"roles":null,"value":null}',
        '{"roles":"","value":"ALL"}',
        {"roles": ""},
    ],
)
def test_unknown_secondary_context_is_not_none(value):
    assert not secondary_roles_disabled(value)


def test_sparse_native_metadata_is_verified_from_cached_results(evidence):
    config, db, report, _, _, _, _ = evidence
    audit = audit_run(db, config, report)
    assert verify_probe(config, audit, "USER")["context"]["PASSAGES"] == 1
    assert audit["secondary_roles"] == "unverified_for_this_run"
    assert audit["complete_candidate_coverage"]
    assert all("CURRENT_USER()" not in c.args[0] for c in db.run.call_args_list)


@pytest.mark.parametrize(
    "field,value",
    [
        ("QUERY_ID", "unrelated"),
        ("USER_NAME", "OTHER"),
        ("ROLE_NAME", "ACCOUNTADMIN"),
        ("WAREHOUSE_NAME", "OTHER_WH"),
        ("EXECUTION_STATUS", "FAIL"),
        ("QUERY_TEXT", "SELECT 'USER' AS USER_NAME"),
        ("START_TIME", "2026-10-14T08:00:15+00:00"),
        ("END_TIME", "2026-10-15T09:00:00+00:00"),
    ],
)
def test_query_history_rejects_wrong_context_or_stale_evidence(evidence, field, value):
    config, db, report, payload, history, _, _ = evidence
    history[field] = value
    with pytest.raises(ValueError, match="history"):
        verify_query(db, config, report, payload)
    assert len(db.run.call_args_list) == 1  # No cached result accepted before history checks.


@pytest.mark.parametrize(
    "field,value",
    [("SECONDARY_ROLES", "{}"), ("ROLE_NAME", "OTHER"), ("PASSAGES", 2), ("DOCUMENTS", 2)],
)
def test_native_context_and_counts_fail_closed(evidence, field, value):
    config, db, report, _, _, context, _ = evidence
    context[field] = value
    with pytest.raises(ValueError, match="context or counts"):
        verify_probe(config, audit_run(db, config, report), "USER")


def test_same_user_historical_or_unrelated_sql_is_not_native_probe(evidence):
    config, db, report, payload, history, _, _ = evidence
    payload["sql"] = history["QUERY_TEXT"] = "SELECT 'USER' AS USER_NAME"
    with pytest.raises(ValueError, match="context aggregate"):
        verify_probe(config, audit_run(db, config, report), "USER")


def test_unknown_search_chunk_fails(evidence):
    config, db, report, _, _, _, row = evidence
    original = db.run.side_effect
    db.run.side_effect = lambda sql, params=None: (
        [{**row, "SHA256": "stale"}]
        if params == ("search-query",) and "RESULT_SCAN" in sql
        else original(sql, params)
    )
    with pytest.raises(ValueError, match="stale"):
        audit_run(db, config, report)


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_text", "wrong_id"])
def test_index_reconciliation_checks_content_not_just_counts(evidence, change):
    config, db, _, _, _, _, row = evidence
    actual = [dict(row)]
    if change == "missing":
        actual = []
    if change == "duplicate":
        actual.append(dict(row))
    if change == "wrong_text":
        actual[0]["CHUNK"] = "stale text"
    if change == "wrong_id":
        actual[0]["CHUNK_ID"] = "other"
    db.run.side_effect = [[row], actual]
    with pytest.raises(ValueError, match="Indexed chunks"):
        verify_index(db, config)


def test_same_count_wrong_inventory_is_not_accepted():
    audit = {
        "sql_queries": [
            {
                "search_lineage_verified": True,
                "rows": [{"DOC_ID": "a", "SOURCE_PATH": "data/wrong.md", "FILE_TYPE": "md"}],
            }
        ]
    }
    with pytest.raises(ValueError, match="exact"):
        verify_inventory(audit, [{"doc_id": "a", "path": "data/right.md", "file_type": "md"}])
    audit["sql_queries"][0]["rows"][0]["SOURCE_PATH"] = "data/right.md"
    verify_inventory(audit, [{"doc_id": "a", "path": "data/right.md", "file_type": "md"}])


def test_citations_resolve_physical_page_and_reject_stale_identity(evidence):
    config, _, _, _, _, _, row = evidence
    citation = {
        "doc_id": "chunk",
        "type": "cortex_search_citation",
        "index": 4,
        "stage_path": "@" + config.stage,
        "relative_path": row["RELATIVE_PATH"],
        "doc_title": "example.md",
    }
    report: dict[str, Any] = {"answer": "Fact.", "annotations": [citation]}
    assert verify_citations(config, report, [row], {"doc": 1})[0]["physical_page"] == 1
    for field, value in [("doc_id", "stale"), ("index", 99), ("relative_path", "wrong")]:
        broken = deepcopy(report)
        broken["annotations"][0][field] = value
        with pytest.raises(ValueError, match="Citation"):
            verify_citations(config, broken, [row], {"doc": 1})


def test_runtime_failure_replaces_stale_evaluation(tmp_path, monkeypatch):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    (tmp_path / "evaluation.json").write_text('{"status":"requires_review"}')

    def failed(*_):
        raise ValueError("runtime denied")

    monkeypatch.setattr("snow_analytical_search.agent.verify_runtime", failed)
    with pytest.raises(ValueError, match="denied"):
        evaluate(config)
    report = json.loads((tmp_path / "evaluation.json").read_text())
    assert report["status"] == "failed"
    assert report["stage"] == "runtime"
    assert report["snapshot_id"] == config.snapshot
    assert list((tmp_path / "evaluations").glob("*.json"))


def test_runtime_does_not_accept_prose_without_sql(tmp_path, monkeypatch):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    monkeypatch.setattr("snow_analytical_search.agent.ask", lambda *_: {"sql_results": []})
    with pytest.raises(ValueError, match="No native SQL"):
        verify_runtime(config)
    assert json.loads((tmp_path / "runtime-verification.json").read_text())["status"] == "failed"


@pytest.mark.parametrize(
    "sql,parents,analytical",
    [
        ("SELECT COUNT(*) FROM TABLE(RESULT_SCAN('q')) /* AI_FILTER(CHUNK) */", {"q"}, False),
        ("SELECT AI_FILTER('mental health','constant') /* RESULT_SCAN('q') */", set(), False),
        ("SELECT 'AI_FILTER(CHUNK)' FROM TABLE(RESULT_SCAN('q'))", {"q"}, False),
        ("SELECT $$AI_FILTER(CHUNK)$$ FROM TABLE(RESULT_SCAN('q'))", {"q"}, False),
        ("SELECT 1 /* outer /* nested */ AI_FILTER(CHUNK) */ -- RESULT_SCAN('q')", set(), False),
        (
            "SELECT AI_FILTER(CONCAT('mental health: ',CHUNK)) FROM TABLE(RESULT_SCAN('q'))",
            {"q"},
            True,
        ),
        ("SELECT AI_AGG(\"CHUNK\", 'instructions') FROM TABLE(RESULT_SCAN('q'))", {"q"}, True),
    ],
)
def test_lineage_ignores_sql_comments_and_literal_function_names(sql, parents, analytical):
    from snow_analytical_search.evidence import sql_lineage

    assert sql_lineage(sql) == (parents, analytical)


def test_citation_page_must_fit_document(evidence):
    config, _, _, _, _, _, row = evidence
    citation = {
        "doc_id": "chunk",
        "type": "cortex_search_citation",
        "index": 4,
        "stage_path": "@" + config.stage,
        "relative_path": row["RELATIVE_PATH"],
        "doc_title": "example.md",
    }
    with pytest.raises(ValueError, match="Citation"):
        verify_citations(config, {"answer": "Fact.", "annotations": [citation]}, [row], {"doc": 0})
