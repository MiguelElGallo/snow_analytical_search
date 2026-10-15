from snow_analytical_search import cloud
from snow_analytical_search.config import Config


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
