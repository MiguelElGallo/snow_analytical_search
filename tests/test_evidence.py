import json
from unittest.mock import MagicMock

import pytest

from snow_analytical_search.agent import IDENTITY_SQL, evaluate, verify_runtime
from snow_analytical_search.config import Config
from snow_analytical_search.db import Database


@pytest.mark.parametrize("failure", [None, "tool_sql", "history_sql"])
def test_runtime_requires_executed_identity_expressions(tmp_path, monkeypatch, failure):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    columns = ["USER_NAME", "ROLE_NAME", "SECONDARY_ROLES", "WAREHOUSE_NAME"]
    values = ["USER", config.runner, '{"roles":"","value":""}', config.warehouse]
    literal_sql = "SELECT 'USER' AS USER_NAME, 'DEMO_RUNNER' AS ROLE_NAME"
    payload = {
        "query_id": "native-identity",
        "sql": literal_sql if failure == "tool_sql" else IDENTITY_SQL,
        "result_set": {
            "resultSetMetaData": {"rowType": [{"name": n} for n in columns]},
            "data": [values],
        },
    }
    monkeypatch.setattr(
        "snow_analytical_search.agent.ask",
        lambda *_: {"sql_results": [{"content": [{"json": payload}]}]},
    )
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.identity = {"USER_NAME": "USER"}
    db.run.return_value = [
        {
            "QUERY_ID": "native-identity",
            "ROLE_NAME": config.runner,
            "WAREHOUSE_NAME": config.warehouse,
            "EXECUTION_STATUS": "SUCCESS",
            "QUERY_TEXT": literal_sql if failure == "history_sql" else IDENTITY_SQL,
        }
    ]
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    if failure:
        with pytest.raises(ValueError):
            verify_runtime(config)
    else:
        assert verify_runtime(config)["status"] == "verified"
    report = json.loads((tmp_path / "runtime-verification.json").read_text())
    assert report["status"] == ("failed" if failure else "verified")


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


def test_missing_analytical_trace_records_failed_acceptance(tmp_path, monkeypatch):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    monkeypatch.setattr("snow_analytical_search.agent.verify_runtime", lambda *_: {})
    monkeypatch.setattr(
        "snow_analytical_search.agent.ask",
        lambda *_: {
            "elapsed_seconds": 1,
            "analytical_sql_observed": False,
        },
    )
    db = MagicMock(spec=Database)
    db.__enter__.return_value = db
    db.run.return_value = []
    monkeypatch.setattr("snow_analytical_search.agent.Database", lambda *_: db)
    with pytest.raises(ValueError, match="analytical trace"):
        evaluate(config)
    report = json.loads((tmp_path / "evaluation.json").read_text())
    assert report["status"] == "failed"
    assert report["stage"] == "analytical_acceptance"
    assert len(report["results"]) == 6
