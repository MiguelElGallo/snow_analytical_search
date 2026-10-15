import json
from copy import deepcopy
from typing import Any, cast
from unittest.mock import MagicMock, Mock

import pytest

from snow_analytical_search.agent import (
    ask,
    specification,
    summarize_response,
    validate_deployment,
    verify_search,
)
from snow_analytical_search.config import Config
from snow_analytical_search.db import Database


def test_summary_rebases_citations_without_mutating_raw_response():
    response: dict[str, Any] = {
        "content": [
            {"type": "text", "text": "First", "annotations": [{"index": 5, "doc_id": "a"}]},
            {"type": "text", "text": ""},
            {"type": "tool_use", "tool_use": {"name": "corpus_search"}},
            {
                "type": "text",
                "text": "Second claim",
                "annotations": [{"index": 6, "doc_id": "b"}, {"doc_id": "no-position"}],
            },
        ]
    }
    original = deepcopy(response)
    summary = summarize_response(response)
    assert summary["answer"] == "First\n\nSecond claim"
    assert summary["annotations"] == [
        {"index": 5, "doc_id": "a"},
        {"index": 13, "doc_id": "b"},
        {"doc_id": "no-position"},
    ]
    assert response == original


def test_analytical_evidence_requires_successful_structured_tool_result():
    answer_only = {"content": [{"type": "text", "text": "I used system_execute_sql."}]}
    assert not summarize_response(answer_only)["analytical_sql_observed"]
    failed = {
        "content": [
            {
                "type": "tool_result",
                "tool_result": {
                    "name": "system_execute_sql",
                    "status": "error",
                },
            }
        ]
    }
    assert not summarize_response(failed)["analytical_sql_observed"]
    passed: dict[str, Any] = {
        "content": [
            {
                "type": "tool_result",
                "tool_result": {
                    "name": "system_execute_sql",
                    "status": "success",
                    "content": [],
                },
            }
        ]
    }
    passed["content"].insert(
        0,
        {"type": "tool_use", "tool_use": {"name": "system_execute_sql", "tool_use_id": "sql-use"}},
    )
    native_result = cast(dict[str, Any], passed["content"][1]["tool_result"])
    native_result["tool_use_id"] = "sql-use"
    assert summarize_response(passed)["sql_execution_observed"]
    assert not summarize_response(passed)["analytical_sql_observed"]
    native_result["content"] = [
        {
            "json": {
                "sql": "SELECT AI_FILTER('mental health', CHUNK) FROM "
                "TABLE(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('DEMO.APP.SERVICE', '{}'))"
            }
        }
    ]
    assert not summarize_response(passed, "DEMO.APP.SERVICE")["analytical_sql_observed"]
    assert not summarize_response(passed, "DEMO.APP.OLD")["analytical_sql_observed"]


def test_search_verification_rejects_stale_snapshot(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)

    class StaleIndex:
        query_id = "test-query"

        def scalar(self, *_):
            return {
                "results": [
                    {
                        "DOC_ID": "id",
                        "SOURCE_PATH": "data/file.md",
                        "SHA256": "hash",
                        "SOURCE_COMMIT": config.source_commit,
                        "SNAPSHOT_ID": "old-snapshot",
                    }
                ]
            }

    with pytest.raises(ValueError, match="stale"):
        verify_search(
            Mock(spec=Database, scalar=StaleIndex().scalar, query_id="test-query"),
            config,
            [
                {
                    "doc_id": "id",
                    "path": "data/file.md",
                    "sha256": "hash",
                }
            ],
        )


def test_agent_exposes_native_analytical_capability_and_stage_citations(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    spec = specification(config)
    assert spec["orchestration"]["capabilities"]["analytical_search"] is True
    assert spec["orchestration"]["tool_not_accessible"] == "reject"
    resource = spec["tool_resources"]["corpus_search"]
    assert resource["max_results"] == 1000
    assert resource["relative_path_column"] == "RELATIVE_PATH"
    assert resource["stage_path"] == "@DEMO.RAW.DOCUMENTS"
    assert "system_execute_sql" not in [t["tool_spec"]["name"] for t in spec["tools"]]


def test_real_trial_error_envelope_is_a_failure_and_is_preserved(tmp_path, monkeypatch):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    response: dict[str, Any] = {"message": "Access denied for trial accounts.", "code": "399504"}
    assert summarize_response(response)["error"] == response["message"]
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.scalar.return_value = response
    db.run.return_value = [{"agent_spec": json.dumps(specification(config))}]
    db.identity = {"ROLE_NAME": config.runner}
    db.query_id = "failed-call"
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    with pytest.raises(ValueError, match="error, warning"):
        ask(config, "What vacation tiers exist?")
    evidence = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert evidence["response"] == response
    assert evidence["query_id"] == "failed-call"
    assert not evidence["analytical_sql_observed"]


@pytest.mark.parametrize("status", [None, "completed", "cancelled", "timed_out", "failed"])
def test_partial_answer_cannot_hide_interrupted_status(tmp_path, monkeypatch, status):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    response: dict[str, Any] = {"content": [{"type": "text", "text": "Some answer text."}]}
    if status is not None:
        response["status"] = status
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.scalar.return_value = response
    db.run.return_value = [{"agent_spec": json.dumps(specification(config))}]
    db.identity = {"ROLE_NAME": config.runner}
    db.query_id = "captured-query"
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    if status in (None, "completed"):
        assert ask(config, "Question")["answer"] == "Some answer text."
    else:
        with pytest.raises(ValueError, match=f"did not complete \\(status={status}\\)"):
            ask(config, "Question")
    evidence = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert evidence["response"] == response
    assert evidence["status"] == status
    assert evidence["query_id"] == "captured-query"


@pytest.mark.parametrize("failure", [None, "unverified_binding", "failed_search", "unrelated_sql"])
def test_persisted_search_analysis_requires_linked_successful_results(failure):
    response: dict[str, Any] = {
        "content": [
            {
                "type": "tool_result",
                "tool_result": {
                    "name": "corpus_search",
                    "type": "cortex_search",
                    "status": "error" if failure == "failed_search" else "success",
                    "content": [
                        {
                            "json": {
                                "search_results_persist": {
                                    "query_id": "search-query",
                                    "sql": "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?)",
                                }
                            }
                        }
                    ],
                },
            },
            {
                "type": "tool_result",
                "tool_result": {
                    "name": "system_execute_sql",
                    "status": "success",
                    "content": [
                        {
                            "json": {
                                "query_id": "ai-query",
                                "sql": "SELECT COUNT(DISTINCT DOC_ID) FROM TABLE(RESULT_SCAN('"
                                + ("other-query" if failure == "unrelated_sql" else "search-query")
                                + "')) WHERE AI_FILTER(CONCAT('Discusses mental health: ', CHUNK))",
                            }
                        }
                    ],
                },
            },
        ]
    }
    for i, block in enumerate(list(response["content"])):
        result = cast(dict[str, Any], block["tool_result"])
        result["tool_use_id"] = f"use-{i}"
    response["content"] = [
        item
        for block in response["content"]
        for item in (
            {
                "type": "tool_use",
                "tool_use": {
                    "name": cast(dict[str, Any], block["tool_result"])["name"],
                    "tool_use_id": cast(dict[str, Any], block["tool_result"])["tool_use_id"],
                },
            },
            block,
        )
    ]
    result = summarize_response(
        response, "DEMO.APP.SERVICE", "" if failure == "unverified_binding" else "corpus_search"
    )
    assert result["analytical_sql_observed"] is (failure is None)


def test_deployment_rejects_lost_capability_or_incomplete_index(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    spec = specification(config)
    agents = [{"agent_spec": json.dumps(spec)}]
    service = {
        "source_data_num_rows": 281,
        "warehouse": config.warehouse,
        "definition": f"SELECT * WHERE SNAPSHOT_ID='{config.snapshot}'",
    }
    validate_deployment(config, spec, agents, [service], 281)
    with pytest.raises(ValueError, match="snapshot"):
        validate_deployment(config, spec, agents, [{**service, "source_data_num_rows": 280}], 281)
    actual = json.loads(json.dumps(spec))
    actual["orchestration"]["capabilities"]["analytical_search"] = False
    with pytest.raises(ValueError, match="specification"):
        validate_deployment(config, spec, [{"agent_spec": json.dumps(actual)}], [service], 281)


@pytest.mark.parametrize(
    "response",
    [
        ["unexpected array"],
        {"content": [{"type": "text", "text": None}]},
        {
            "content": [
                {"type": "tool_use", "tool_use": {"name": "corpus_search", "tool_use_id": "a"}},
                {
                    "type": "tool_result",
                    "tool_result": {
                        "name": "corpus_search",
                        "tool_use_id": "a",
                        "type": "cortex_search",
                        "status": "success",
                        "content": [{"json": None}],
                    },
                },
            ]
        },
    ],
)
def test_malformed_response_is_saved_before_parsing(tmp_path, monkeypatch, response):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.scalar.return_value = response
    db.run.return_value = [{"agent_spec": json.dumps(specification(config))}]
    db.identity = {"ROLE_NAME": config.runner}
    db.query_id = "raw-query"
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    with pytest.raises(ValueError, match="Malformed"):
        ask(config, "Question")
    artifact = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert artifact["response"] == response
    assert artifact["parse_error"]
    assert artifact["status"] == "failed"


def test_unmatched_native_result_is_not_execution_evidence():
    result = {
        "type": "tool_result",
        "tool_result": {
            "name": "system_execute_sql",
            "status": "success",
            "tool_use_id": "other",
            "content": [],
        },
    }
    response: dict[str, Any] = {
        "content": [
            {
                "type": "tool_use",
                "tool_use": {"name": "system_execute_sql", "tool_use_id": "expected"},
            },
            result,
        ]
    }
    assert not summarize_response(response)["sql_execution_observed"]


def test_ask_rejects_stale_instructions_even_when_snapshot_matches(tmp_path, monkeypatch):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    spec = specification(config)
    spec["instructions"]["response"] = "Old instructions"
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.run.return_value = [{"agent_spec": json.dumps(spec)}]
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    with pytest.raises(ValueError, match="run deploy"):
        ask(config, "Question")
    db.scalar.assert_not_called()
