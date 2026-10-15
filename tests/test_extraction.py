import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from snow_analytical_search import cloud
from snow_analytical_search.config import Config
from snow_analytical_search.extraction import (
    checked_chunks,
    checked_parse,
    chunk_id,
    chunks,
    parse_path,
    pdf_pages,
    provenance,
    text_pages,
)


def envelope(pages=None, count=2):
    return {
        "error": None,
        "metadata": {"pageCount": count},
        "value": {"pages": pages or [{"index": 0, "content": "A"}, {"index": 1, "content": "B"}]},
    }


def test_physical_page_numbering():
    assert pdf_pages(envelope()) == [(1, "A"), (2, "B")]


def test_filtered_native_ocr_retains_original_page_numbers():
    result = envelope(
        pages=[{"index": 2, "content": "Legend"}, {"index": 3, "content": "Axis"}], count=10
    )
    assert pdf_pages(result, expected_indices=[2, 3], expected_count=10) == [
        (3, "Legend"),
        (4, "Axis"),
    ]
    with pytest.raises(ValueError):
        pdf_pages(result)
    with pytest.raises(ValueError):
        pdf_pages(result, expected_indices=[2, 4], expected_count=10)
    with pytest.raises(ValueError):
        pdf_pages(result, expected_indices=[2, 3], expected_count=9)


@pytest.mark.parametrize(
    "result",
    [
        {"error": "Parse failed", "value": None},
        {"metadata": None, "value": {"pages": []}},
        {"metadata": {"pageCount": "2"}, "value": {"pages": []}},
        {"metadata": {"pageCount": 1}, "value": {"pages": [None]}},
        envelope(count=3),
        envelope(pages=[{"index": 0, "content": "A"}, {"index": 0, "content": "B"}]),
        envelope(pages=[{"index": 0, "content": "A"}, {"index": 1, "content": ""}]),
        envelope(
            pages=[{"index": 0, "content": "A"}, {"index": 1, "content": "B", "error": "bad"}]
        ),
    ],
)
def test_partial_or_failed_extractions_do_not_pass(result):
    with pytest.raises(ValueError):
        pdf_pages(result)


def test_json_is_inert_source_text():
    pages = text_pages(b'{"query":"DELETE FROM users"}', "json")
    assert pages == [(1, '{\n  "query": "DELETE FROM users"\n}')]


def test_chunks_are_bounded_and_cover_content_without_losing_tail():
    text = "".join(f"Line {i}: content for testing.\n" for i in range(1000))
    parts = chunks(text, size=500, overlap=50)
    assert max(map(len, parts)) <= 500
    assert all(f"Line {i}:" in "\n".join(parts) for i in range(1000))
    assert parts[-1].endswith("Line 999: content for testing.")
    assert chunk_id("a", "b", 1, 0) != chunk_id("a", "b", 2, 0)
    assert chunk_id("a", "b", 1, 0) == chunk_id("a", "b", 1, 0)


def test_invalid_chunk_overlap():
    with pytest.raises(ValueError):
        chunks("text", 2, 2)


def test_cached_parse_binds_source_and_parser(tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path, "local")
    entry = {"sha256": "123", "path": "data/test.pdf"}
    result = {**envelope(), "provenance": provenance(config, entry)}
    assert checked_parse(result, config, entry) == [(1, "A"), (2, "B")]
    with pytest.raises(ValueError, match="provenance"):
        checked_parse(result, config, {**entry, "sha256": "456"})
    native = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path, "snowflake")
    assert native.snapshot != config.snapshot
    with pytest.raises(ValueError, match="provenance"):
        checked_parse(result, native, entry)


def test_historical_local_snapshot_is_unchanged(tmp_path):
    commit = "558ffd397eddcfe4da5c85ebc285796b367eb9b2"
    local = Config("test", "ACCT", "DEMO", commit, tmp_path, "local")
    native = Config("test", "ACCT", "DEMO", commit, tmp_path)
    assert local.snapshot == "780a4bc67bc603d9a00aeaeb"
    assert native.snapshot != local.snapshot
    assert "split_text_recursive_character" in native.pipeline_identity
    assert replace(native, native_ocr=False).snapshot == "c28795214ae6b7b5fae14d70"
    assert replace(native, native_ocr=False).snapshot != native.snapshot


def native_row(content, index=0, page=1):
    return {"PAGE_NUMBER": page, "CHUNK_INDEX": index, "CHUNK": content, "CHUNK_TYPE": "VARCHAR"}


def test_native_chunks_preserve_repeated_text_overlap_and_page_boundaries():
    pages = [(1, "x" * 6500), (2, "A table\n  | value | 50 |\n")]
    rows = [native_row("x" * 3500), native_row("x" * 3300, 1), native_row(pages[1][1], page=2)]
    assert len(checked_chunks(pages, rows)) == 3


def test_native_chunks_accept_short_repeated_tail():
    pages = [(1, "prefix " + "repeat " * 500)]
    rows = [native_row("prefix " + "repeat " * 499), native_row("repeat", 1)]
    assert len(checked_chunks(pages, rows)) == 2


def test_native_chunks_keep_ambiguous_overlap_positions_until_final_tail():
    text = "A" * 9000
    rows = [
        native_row(text[:3500]),
        native_row(text[3200:6700], 1),
        native_row(text[6400:], 2),
    ]
    assert len(checked_chunks([(1, text)], rows)) == 3


def test_native_ocr_composition_preserves_layout_and_original_query_id(monkeypatch, tmp_path):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    entry = {"sha256": "hash", "path": "data/a.pdf"}
    layout = replace(config, native_ocr=False)
    target = parse_path(layout, entry)
    target.parent.mkdir(parents=True)
    raw = '{"parse_query_id": "original-layout-query"}\n'
    target.write_text(raw)
    pages = [(1, "| Accurate | Table |"), (2, "## Chart\n![img](img.jpeg)")]
    monkeypatch.setattr(cloud, "extract", lambda *_: pages)
    db = Mock(query_id="new-ocr-query")
    db.scalar.return_value = envelope(pages=[{"index": 1, "content": "2018 2019 Axis"}], count=2)
    result = cloud.enriched_native_parse(db, config, entry)
    composed = checked_parse(result, config, entry)
    assert composed[0] == pages[0]
    assert composed[1][1].startswith(pages[1][1])
    assert composed[1][1].endswith("2018 2019 Axis")
    assert result["inputs"]["layout"]["query_id"] == "original-layout-query"
    assert result["inputs"]["ocr"]["query_id"] == "new-ocr-query"
    assert target.read_text() == raw
    options = json.loads(db.scalar.call_args.args[1][2])
    assert options == {"mode": "OCR", "page_filter": [{"start": 1, "end": 2}]}
    db.scalar.reset_mock()
    assert cloud.enriched_native_parse(db, config, entry) == result
    db.scalar.assert_not_called()


@pytest.mark.parametrize(
    "pages,rows",
    [
        ([(1, "first middle last")], [native_row("first last")]),
        ([(1, "first middle last")], [native_row("first middle")]),
        ([(1, "text"), (2, "text")], [native_row("text")]),
        ([(1, "text")], [native_row("text", index=1)]),
        ([(1, "text")], [native_row("text"), native_row("text")]),
        ([(1, "text")], [native_row("text", page=2)]),
        ([(1, "text")], [native_row(123)]),
        ([(1, "text")], [native_row(" ")]),
        ([(1, "x" * 3501)], [native_row("x" * 3501)]),
        ([(1, "text")], []),
    ],
)
def test_native_chunk_gaps_and_malformed_results_are_rejected(pages, rows):
    with pytest.raises(ValueError):
        checked_chunks(pages, rows)
