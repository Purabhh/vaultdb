import json
from pathlib import Path

from vaultdb.config import (
    BASELINE,
    IndexOptions,
    VaultInfo,
    config_path,
    data_dir,
    db_path,
    import_legacy_echidna,
    load_vaults,
    save_vaults,
)


def test_data_dir_honors_env_override(data_dir: Path) -> None:
    assert globals()["data_dir"]() == data_dir
    assert config_path() == data_dir / "vaults.json"
    assert db_path() == data_dir / "vaultdb.sqlite3"


def test_save_then_load_roundtrip(data_dir: Path) -> None:
    save_vaults({"Components": VaultInfo("Components", "/x/Components", 40)})
    assert load_vaults()["Components"].note_count == 40
    saved = json.loads(config_path().read_text())
    assert saved["vaults"]["Components"]["source_path"] == "/x/Components"


def test_load_missing_or_corrupt_returns_empty(data_dir: Path) -> None:
    assert load_vaults() == {}
    config_path().write_text("{not json")
    assert load_vaults() == {}


def test_import_legacy_echidna(data_dir: Path) -> None:
    legacy = data_dir.parent / "echidna"
    legacy.mkdir()
    (legacy / "vaults.json").write_text(
        json.dumps({"vaults": {"C": {"name": "C", "source_path": "/c", "note_count": 3}}})
    )
    assert import_legacy_echidna() is True
    assert load_vaults()["C"].source_path == "/c"
    assert import_legacy_echidna() is False  # vaults.json now exists


def test_import_legacy_without_echidna_is_noop(data_dir: Path) -> None:
    assert import_legacy_echidna() is False
    assert load_vaults() == {}


def test_baseline_options_all_off() -> None:
    assert BASELINE == IndexOptions(False, False, False, False, False)
    assert IndexOptions() == IndexOptions(True, True, True, True, False)
