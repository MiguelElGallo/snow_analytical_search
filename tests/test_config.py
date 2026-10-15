from pathlib import Path

import pytest

from snow_analytical_search.config import load_config


@pytest.mark.parametrize("location", [None, "~/private-evidence", "relative-evidence"])
def test_evidence_paths_resolve_without_depending_on_checkout(tmp_path, location):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "demo.toml"
    text = 'connection="test"\nexpected_account="ACCT"\nprefix="DEMO"\n'
    text += f'source_commit="{"a" * 40}"\n'
    if location is not None:
        text += f'state_dir="{location}"\n'
    path.write_text(text)
    expected = (
        Path.home() / ".local/state/snow-analytical-search"
        if location is None
        else Path.home() / "private-evidence"
        if location.startswith("~")
        else config_dir / location
    )
    assert load_config(path).state_dir == expected
