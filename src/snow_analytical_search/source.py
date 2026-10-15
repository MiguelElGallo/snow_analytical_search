"""Download all files from a pinned public Git tree and verify their bytes."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import REPOSITORY, Config

MAX_FILE_BYTES = 50 * 1024 * 1024


def fetch(url: str, limit: int = MAX_FILE_BYTES) -> bytes:
    request = Request(url, headers={"User-Agent": "snow-analytical-search/0.1"})
    with urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Download exceeds {limit} bytes: {url}")
    return data


def safe_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if (
        not path.startswith("data/")
        or ".." in parts
        or str(PurePosixPath(path)) != path
        or not re.fullmatch(r"[A-Za-z0-9_./ -]+", path)
    ):
        raise ValueError(f"Unsupported or unsafe source path: {path!r}")
    return path


def inventory(tree: dict[str, Any]) -> list[dict[str, Any]]:
    if tree.get("truncated") is not False:
        raise ValueError("GitHub tree is truncated or missing completeness information")
    files = []
    for entry in tree["tree"]:
        if not entry["path"].startswith("data/") or entry["type"] == "tree":
            continue
        path = safe_path(entry["path"])
        if entry["type"] != "blob" or entry.get("mode") not in {"100644", "100755"}:
            raise ValueError(f"Not a regular source file: {path}")
        if PurePosixPath(path).suffix.lower() not in {".pdf", ".md", ".json"}:
            raise ValueError(f"No extractor for {path}; refusing an incomplete ingestion")
        if not 0 < entry["size"] <= MAX_FILE_BYTES:
            raise ValueError(f"Unsupported file size: {path}")
        files.append({"path": path, "git_blob": entry["sha"], "size": entry["size"]})
    if not files or len({f["path"] for f in files}) != len(files):
        raise ValueError("Empty or duplicate source inventory")
    return sorted(files, key=lambda f: f["path"])


def check_bytes(data: bytes, entry: dict[str, Any]) -> str:
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != entry["size"] or blob != entry["git_blob"]:
        raise ValueError(f"Source integrity check failed: {entry['path']}")
    return hashlib.sha256(data).hexdigest()


def download(config: Config) -> list[dict[str, Any]]:
    root = config.corpus_dir
    root.mkdir(parents=True, exist_ok=True)
    tree = json.loads(
        fetch(
            f"https://api.github.com/repos/{REPOSITORY}/git/trees/{config.source_commit}?recursive=1"
        )
    )
    entries = inventory(tree)
    for entry in entries:
        path = root / entry["path"]
        if path.is_symlink():
            raise ValueError(f"Refusing symlink: {path}")
        data = (
            path.read_bytes()
            if path.exists()
            else fetch(
                f"https://raw.githubusercontent.com/{REPOSITORY}/{config.source_commit}/"
                + quote(entry["path"])
            )
        )
        entry["sha256"] = check_bytes(data, entry)
        entry["doc_id"] = hashlib.sha256(entry["path"].encode()).hexdigest()
        entry["source_url"] = (
            f"https://github.com/{REPOSITORY}/blob/{config.source_commit}/" + quote(entry["path"])
        )
        entry["file_type"] = path.suffix[1:].lower()
        entry["kind"] = (
            "query_example"
            if path.name == "query.json"
            else "json_example"
            if path.suffix == ".json"
            else "document"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "UPSTREAM_LICENSE").write_bytes(
        fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/{config.source_commit}/LICENSE")
    )
    write_json(root / "manifest.json", {"commit": config.source_commit, "files": entries})
    return entries


def read_manifest(config: Config) -> list[dict[str, Any]]:
    manifest = json.loads((config.corpus_dir / "manifest.json").read_text())
    if manifest["commit"] != config.source_commit:
        raise ValueError("Manifest commit does not match configuration")
    authoritative = inventory(
        json.loads(
            fetch(
                f"https://api.github.com/repos/{REPOSITORY}/git/trees/{config.source_commit}?recursive=1"
            )
        )
    )
    actual = manifest["files"]
    expected = {(e["path"], e["git_blob"], e["size"]) for e in authoritative}
    observed = {(e["path"], e["git_blob"], e["size"]) for e in actual}
    if len(actual) != len(expected) or expected != observed:
        raise ValueError("Local manifest does not cover the complete pinned Git tree")
    for entry in manifest["files"]:
        safe_path(entry["path"])
        source_url = f"https://github.com/{REPOSITORY}/blob/{config.source_commit}/" + quote(
            entry["path"]
        )
        path = PurePosixPath(entry["path"])
        kind = (
            "query_example"
            if path.name == "query.json"
            else "json_example"
            if path.suffix == ".json"
            else "document"
        )
        if (
            entry["doc_id"] != hashlib.sha256(entry["path"].encode()).hexdigest()
            or entry["source_url"] != source_url
            or entry["kind"] != kind
            or entry["file_type"] != path.suffix[1:].lower()
        ):
            raise ValueError("Manifest derived metadata does not match source paths")
        if check_bytes((config.corpus_dir / entry["path"]).read_bytes(), entry) != entry["sha256"]:
            raise ValueError("SHA-256 mismatch")
    return manifest["files"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")
