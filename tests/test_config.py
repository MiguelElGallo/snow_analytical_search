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


@pytest.mark.parametrize("legacy_parser", [None, "snowflake"])
def test_existing_native_configuration_keeps_identity(tmp_path, legacy_parser):
    path = tmp_path / "demo.toml"
    text = 'connection="test"\nexpected_account="ACCT"\nprefix="DEMO"\n'
    text += 'source_commit="558ffd397eddcfe4da5c85ebc285796b367eb9b2"\n'
    if legacy_parser is not None:
        text += f'pdf_parser="{legacy_parser}"\n'
    path.write_text(text)
    assert load_config(path).snapshot == "8f805241c0e87c37f920ab29"


@pytest.mark.parametrize("value", ['"local"', '"unknown"', "false", "[]"])
def test_retired_parser_configuration_fails_before_cloud_access(tmp_path, monkeypatch, value):
    from snow_analytical_search import cli

    path = tmp_path / "demo.toml"
    path.write_text(
        'connection="test"\nexpected_account="ACCT"\nprefix="DEMO"\n'
        f'source_commit="{"a" * 40}"\npdf_parser={value}\n'
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected configuration must not open a connection")

    monkeypatch.setattr(cli, "Database", forbidden)
    monkeypatch.setattr(cli, "ingest", forbidden)
    monkeypatch.setattr("sys.argv", ["sas", "--config", str(path), "ingest"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1


def test_removed_extraction_command_is_rejected_before_loading_config(monkeypatch):
    from snow_analytical_search import cli

    def forbidden(*args, **kwargs):
        raise AssertionError("Removed command must not load configuration")

    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr("sys.argv", ["sas", "extract-pdfs"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
