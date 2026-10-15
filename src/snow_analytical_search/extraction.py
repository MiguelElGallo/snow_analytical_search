"""Validate complete PDF extraction and make bounded, traceable chunks."""

import hashlib
import json
from typing import Any

from .config import CHUNK_OVERLAP, CHUNK_SIZE, PYPDF_VERSION, Config
from .source import read_manifest, write_json


def decode(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def pdf_pages(
    result: Any, *, expected_indices: list[int] | None = None, expected_count: int | None = None
) -> list[tuple[int, str]]:
    envelope = decode(result)
    if not isinstance(envelope, dict) or envelope.get("error"):
        error = envelope.get("error") if isinstance(envelope, dict) else "invalid envelope"
        raise ValueError(f"Document parsing failed: {error}")
    value = decode(envelope.get("value"))
    if not isinstance(value, dict) or value.get("error") or value.get("errorInformation"):
        raise ValueError("Missing or failed PDF parse value")
    metadata = envelope.get("metadata")
    count = metadata.get("pageCount") if isinstance(metadata, dict) else None
    if type(count) is not int or count < 1:
        raise ValueError("PDF page count mismatch or missing metadata.pageCount")
    wanted = expected_indices if expected_indices is not None else range(count)
    pages = value.get("pages", [])
    if (
        (expected_count is not None and count != expected_count)
        or not wanted
        or len(set(wanted)) != len(wanted)
        or any(index < 0 or index >= count for index in wanted)
        or not isinstance(pages, list)
        or len(pages) != len(wanted)
        or any(not isinstance(page, dict) for page in pages)
    ):
        raise ValueError("PDF page count mismatch or missing metadata.pageCount")
    indices = [page.get("index") for page in pages]
    if any(type(index) is not int for index in indices) or sorted(indices) != sorted(wanted):
        raise ValueError("Missing or duplicate PDF page indices")
    result_pages = []
    for page in sorted(pages, key=lambda p: p["index"]):
        if page.get("error") or page.get("errorInformation"):
            raise ValueError(f"PDF page {page['index']} failed")
        content = page.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"PDF page {page['index'] + 1} is empty; manual inspection required")
        result_pages.append((page["index"] + 1, content))
    return result_pages


def provenance(config: Config, entry: dict[str, Any]) -> dict[str, str]:
    return {"sha256": entry["sha256"], "pipeline": config.pipeline_identity}


def checked_parse(result: Any, config: Config, entry: dict[str, Any]) -> list[tuple[int, str]]:
    result = decode(result)
    if not isinstance(result, dict) or result.get("provenance") != provenance(config, entry):
        raise ValueError(f"PDF parse provenance mismatch: {entry['path']}")
    return pdf_pages(result)


def parse_path(config: Config, entry: dict[str, Any]):
    return config.state_dir / "parses" / config.snapshot / f"{entry['sha256']}.json"


def extract_pdfs(config: Config) -> dict[str, Any]:
    """Credential-free extraction; source inventory verification still needs GitHub access."""
    if config.pdf_parser != "local":
        raise ValueError("extract-pdfs requires pdf_parser=local")
    # Lazy import lets the trusted Snowflake CLI runtime ingest already-extracted pages.
    import pypdf

    if pypdf.__version__ != PYPDF_VERSION:
        raise ValueError(f"Expected pypdf {PYPDF_VERSION}, found {pypdf.__version__}")
    reports = []
    for entry in read_manifest(config):
        if entry["file_type"] != "pdf":
            continue
        target = parse_path(config, entry)
        reused = target.exists()
        if reused:
            result = json.loads(target.read_text())
        else:
            reader = pypdf.PdfReader(config.corpus_dir / entry["path"], strict=True)
            result = {
                "provenance": provenance(config, entry),
                "error": None,
                "metadata": {"pageCount": len(reader.pages)},
                "value": {
                    "pages": [
                        {
                            "index": index,
                            "content": page.extract_text(
                                extraction_mode="layout",
                                layout_mode_strip_rotated=False,
                                layout_mode_space_vertically=True,
                            ),
                        }
                        for index, page in enumerate(reader.pages)
                    ]
                },
            }
        pages = checked_parse(result, config, entry)
        if not reused:
            write_json(target, result)
        reports.append({"path": entry["path"], "pages": len(pages), "reused": reused})
    report = {"parser": config.parser_identity, "files": reports}
    write_json(config.state_dir / "extraction.json", report)
    return report


def text_pages(data: bytes, file_type: str) -> list[tuple[int, str]]:
    text = data.decode("utf-8")
    if file_type == "json":
        text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    if not text.strip():
        raise ValueError("Empty source text")
    return [(1, text)]


def chunks(text: str, size: int = 3500, overlap: int = 300) -> list[str]:
    if not 0 <= overlap < size:
        raise ValueError("Chunk overlap must be smaller than the positive chunk size")
    output = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            output.append(part)
        if end == len(text):
            break
        start = end - overlap
    return output


def chunk_id(snapshot: str, doc_id: str, page: int, index: int) -> str:
    return hashlib.sha256(f"{snapshot}:{doc_id}:{page}:{index}".encode()).hexdigest()


def checked_chunks(
    pages: list[tuple[int, str]], rows: list[dict[str, Any]]
) -> list[tuple[int, int, str]]:
    """Reject malformed, reordered, oversized, or incomplete native splitting."""
    by_page: dict[int, list[tuple[int, str]]] = {page: [] for page, _ in pages}
    if len(by_page) != len(pages) or not pages:
        raise ValueError("Missing or duplicate source pages for chunking")
    result = []
    for row in rows:
        page, index, content = row.get("PAGE_NUMBER"), row.get("CHUNK_INDEX"), row.get("CHUNK")
        if (
            type(page) is not int
            or page not in by_page
            or type(index) is not int
            or index < 0
            or row.get("CHUNK_TYPE") != "VARCHAR"
            or not isinstance(content, str)
            or not content.strip()
            or len(content) > CHUNK_SIZE
        ):
            raise ValueError("Invalid native chunk page, index, type, or content")
        by_page[page].append((index, content))
        result.append((page, index, content))
    if [(p, i) for p, i, _ in result] != sorted((p, i) for p, i, _ in result):
        raise ValueError("Native chunks are not ordered by page and array index")
    for page, text in pages:
        parts = by_page[page]
        if not parts or [index for index, _ in parts] != list(range(len(parts))):
            raise ValueError(f"Missing or duplicate native chunks on page {page}")
        compact = "".join(text.split())
        # Repeated text can have several valid overlap positions. Keep each
        # possible endpoint; a greedy match can reject a complete later tail.
        covered = {0}
        for _, content in parts:
            part = "".join(content.split())
            next_covered = set()
            for end in covered:
                start = max(0, end - CHUNK_OVERLAP)
                while (match := compact.find(part, start, end + len(part))) >= 0:
                    next_covered.add(max(end, match + len(part)))
                    start = match + 1
            if not next_covered:
                raise ValueError(f"Native chunk content gap or alteration on page {page}")
            covered = next_covered
        if len(compact) not in covered:
            raise ValueError(f"Native chunks omit the end of page {page}")
    return result
