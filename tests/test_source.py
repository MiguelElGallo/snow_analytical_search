import hashlib

import pytest

from snow_analytical_search.config import Config, identifier, literal
from snow_analytical_search.source import check_bytes, inventory, safe_path


def entry(path="data/nested/example.json", data=b"{}"):
    return {
        "path": path,
        "mode": "100644",
        "type": "blob",
        "size": len(data),
        "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
    }


def test_recursive_inventory_keeps_nested_paths_and_rejects_missing_coverage():
    files = inventory({"truncated": False, "tree": [entry(), entry("data/main.md")]})
    assert [f["path"] for f in files] == ["data/main.md", "data/nested/example.json"]
    with pytest.raises(ValueError, match="truncated"):
        inventory({"truncated": True, "tree": [entry()]})
    with pytest.raises(ValueError, match="extractor"):
        inventory({"truncated": False, "tree": [entry("data/new.doc")]})


@pytest.mark.parametrize(
    "path", ["data/../secret", "/data/a.pdf", "data/a';drop.pdf", "data//a.pdf"]
)
def test_unsafe_paths_rejected(path):
    with pytest.raises(ValueError):
        safe_path(path)


def test_source_integrity_detects_same_size_corruption():
    original = entry()
    manifest = {"path": original["path"], "size": 2, "git_blob": original["sha"]}
    assert check_bytes(b"{}", manifest) == hashlib.sha256(b"{}").hexdigest()
    with pytest.raises(ValueError, match="integrity"):
        check_bytes(b"[]", manifest)


def test_sql_identifiers_and_literals():
    assert identifier("DEMO_123") == "DEMO_123"
    assert literal("O'Brien\\sample") == "'O''Brien\\\\sample'"
    with pytest.raises(ValueError):
        identifier("DEMO; DROP DATABASE X")


def test_snapshot_changes_with_source(tmp_path):
    old = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    new = Config("test", "ACCT", "DEMO", "b" * 40, tmp_path)
    assert old.snapshot != new.snapshot
    assert old.service != new.service
