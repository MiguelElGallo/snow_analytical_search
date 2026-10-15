import json
from unittest.mock import Mock

import pytest

from snow_analytical_search import cloud
from snow_analytical_search.config import Config
from snow_analytical_search.extraction import parse_path, provenance


def test_unchanged_ingest_reuses_completed_document(monkeypatch, tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    entry = {"path": "data/a.pdf", "sha256": "hash", "doc_id": "id"}

    class ExistingDatabase:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def run(self, *_):
            return [{"SHA256": "hash"}]

    def unexpected_parse(*_):
        raise AssertionError("Unchanged document must not repeat paid parsing")

    monkeypatch.setattr(cloud, "Database", ExistingDatabase)
    monkeypatch.setattr(cloud, "read_manifest", lambda _: [entry])
    monkeypatch.setattr(cloud, "upload", lambda *_: None)
    monkeypatch.setattr(cloud, "extract", unexpected_parse)
    monkeypatch.setattr(cloud, "verify_corpus", lambda *_: {"documents": 1})
    result = cloud.ingest(config)
    assert result["processed"] == 0
    assert result["reused"] == 1


@pytest.mark.parametrize(
    "file_type,format_name", [("pdf", "markdown"), ("md", "markdown"), ("json", "none")]
)
def test_every_file_type_uses_native_splitter_with_page_provenance(
    tmp_path, file_type, format_name
):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    entry = {
        "path": f"data/a.{file_type}",
        "sha256": "hash",
        "doc_id": "id",
        "source_url": "https://example.com/source",
        "file_type": file_type,
        "kind": "document",
        "size": 20,
    }
    pages = [(1, "First page"), (2, "Second page")] if file_type == "pdf" else [(1, "Source text")]
    rows = [
        {"PAGE_NUMBER": page, "CHUNK_INDEX": 0, "CHUNK": text, "CHUNK_TYPE": "VARCHAR"}
        for page, text in pages
    ]
    db = Mock(query_id="native-split-query")
    db.run.side_effect = lambda sql, *_: rows if "SPLIT_TEXT_RECURSIVE_CHARACTER" in sql else []
    assert cloud._insert_document(db, config, entry, pages) == len(pages)
    sql, params = db.run.call_args_list[0].args
    assert "SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER" in sql
    assert params == (json.dumps(pages), format_name)
    inserts = [call for call in db.run.call_args_list if ".CORPUS.CHUNKS SELECT" in call.args[0]]
    stored = json.loads(inserts[0].args[1][0])
    assert [(row[9], row[3]) for row in stored] == pages


@pytest.mark.parametrize("native_ocr", [True, False])
def test_native_parse_cache_is_reused_without_parsing(tmp_path, native_ocr):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path, native_ocr=native_ocr)
    entry = {"path": "data/a.pdf", "sha256": "hash", "file_type": "pdf"}
    result = {
        "provenance": provenance(config, entry),
        "metadata": {"pageCount": 1},
        "value": {"pages": [{"index": 0, "content": "Existing native text"}]},
    }
    db = Mock()
    db.run.return_value = [{"RESULT": result}]
    assert cloud.extract(db, config, entry) == [(1, "Existing native text")]
    db.scalar.assert_not_called()
    db.run.assert_called_once()
    assert db.run.call_args.args[1] == ("hash", config.pipeline_identity)
    assert json.loads(parse_path(config, entry).read_text()) == result


def test_native_pdf_error_is_preserved_and_never_loaded(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path, native_ocr=False)
    entry = {"path": "data/a.pdf", "sha256": "hash", "file_type": "pdf"}
    db = Mock(query_id="failed-native-parse")
    db.run.return_value = []
    db.scalar.return_value = {"error": "AI parsing unavailable", "value": None}
    with pytest.raises(ValueError, match="Document parsing failed"):
        cloud.extract(db, config, entry)
    assert "AI_PARSE_DOCUMENT" in db.scalar.call_args.args[0]
    assert db.scalar.call_count == 1
    assert json.loads(parse_path(config, entry).read_text())["error"] == "AI parsing unavailable"
    assert all(call.args[0].startswith("SELECT RESULT") for call in db.run.call_args_list)


@pytest.mark.parametrize("failure", ["native_error", "invalid_native_output"])
def test_native_splitter_failure_cannot_replace_stored_corpus(tmp_path, failure):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    entry = {"path": "data/a.md", "sha256": "hash", "doc_id": "id", "file_type": "md"}
    db = Mock(query_id="native-split-query")
    if failure == "native_error":
        db.run.side_effect = ValueError("Native splitter unavailable")
    else:
        db.run.return_value = []
    with pytest.raises(ValueError):
        cloud._insert_document(db, config, entry, [(1, "Source text")])
    db.run.assert_called_once()
    assert "SPLIT_TEXT_RECURSIVE_CHARACTER" in db.run.call_args.args[0]
