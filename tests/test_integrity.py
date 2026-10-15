import json
from unittest.mock import Mock

import pytest

from snow_analytical_search import cloud, source
from snow_analytical_search.config import Config
from snow_analytical_search.db import Database


def test_missing_manifest_entry_rejected_against_pinned_tree(monkeypatch, tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    config.corpus_dir.mkdir(parents=True)
    (config.corpus_dir / "manifest.json").write_text(
        json.dumps({"commit": config.source_commit, "files": []})
    )
    tree = {
        "truncated": False,
        "tree": [
            {"path": "data/file.md", "type": "blob", "mode": "100644", "size": 2, "sha": "blob"}
        ],
    }
    monkeypatch.setattr(source, "fetch", lambda _: json.dumps(tree).encode())
    with pytest.raises(ValueError, match="complete pinned"):
        source.read_manifest(config)


def test_skipped_upload_still_verifies_remote_bytes(monkeypatch, tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    db = Mock(spec=Database)
    db.run.return_value = [{"status": "SKIPPED"}]
    verify = Mock(side_effect=ValueError("Source integrity check failed"))
    monkeypatch.setattr(cloud, "verify_staged_bytes", verify)
    with pytest.raises(ValueError, match="integrity"):
        cloud.upload(db, config, {"path": "data/file.md"})
    verify.assert_called_once()


@pytest.mark.parametrize("fault", ["orphan_chunk", "missing_page", "extra_stage_file"])
def test_corpus_coverage_rejects_unexpected_or_missing_rows(tmp_path, fault):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    entry = {"path": "data/a.md", "sha256": "hash", "doc_id": "id", "size": 1}
    document = {
        "SOURCE_PATH": "data/a.md",
        "SHA256": "hash",
        "DOC_ID": "id",
        "CHUNK_COUNT": 1,
        "PAGE_COUNT": 1,
    }

    def query(sql, *_):
        if ".DOCUMENTS " in sql:
            return [document]
        if ".CHUNKS " in sql:
            result = [{"DOC_ID": "id", "N": 1, "DISTINCT_N": 1}]
            if fault == "orphan_chunk":
                result.append({"DOC_ID": "extra", "N": 1, "DISTINCT_N": 1})
            return result
        if ".PAGES " in sql:
            return (
                []
                if fault == "missing_page"
                else [{"DOC_ID": "id", "PAGE_NUMBER": 1, "CONTENT": "a"}]
            )
        if sql.startswith("LIST"):
            return [{"name": "unexpected", "size": 1}] * 2
        raise AssertionError(sql)

    db = Mock(spec=Database, run=query)
    with pytest.raises(ValueError):
        cloud.verify_corpus(db, config, [entry])
