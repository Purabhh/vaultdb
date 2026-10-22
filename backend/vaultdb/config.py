"""Where vaultdb keeps its data, the list of vaults, and indexing options."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import platformdirs

APP_NAME = "vaultdb"
LEGACY_APP_NAME = "echidna"  # an older build's name; its vault list is imported once


def data_dir() -> Path:
    """The app's data folder (created if missing). VAULTDB_DATA_DIR overrides it."""
    override = os.environ.get("VAULTDB_DATA_DIR")
    path = Path(override) if override else Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "vaults.json"


def db_path() -> Path:
    return data_dir() / "vaultdb.sqlite3"


@dataclass
class VaultInfo:
    name: str
    source_path: str
    note_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _read_vaults(path: Path) -> dict[str, VaultInfo]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            name: VaultInfo(v["name"], v["source_path"], int(v.get("note_count", 0)))
            for name, v in raw.get("vaults", {}).items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def load_vaults() -> dict[str, VaultInfo]:
    return _read_vaults(config_path())


def save_vaults(vaults: dict[str, VaultInfo]) -> None:
    payload = {"vaults": {name: v.to_dict() for name, v in vaults.items()}}
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(config_path())


def import_legacy_echidna() -> bool:
    """Copy the old echidna build's vault list if vaultdb has none yet. Returns True if it imported."""
    if config_path().exists():
        return False
    legacy = data_dir().parent / LEGACY_APP_NAME / "vaults.json"
    if not legacy.is_file():
        return False
    vaults = _read_vaults(legacy)
    if not vaults:
        return False
    save_vaults(vaults)
    return True


@dataclass(frozen=True)
class IndexOptions:
    """Switches for how notes are indexed and searched. BASELINE reproduces the old Rust behavior."""

    keep_code: bool = True
    use_prefixes: bool = True
    component_cards: bool = True
    hybrid: bool = True
    llm_descriptions: bool = False


BASELINE = IndexOptions(False, False, False, False, False)

__all__ = [
    "APP_NAME", "BASELINE", "IndexOptions", "VaultInfo", "config_path", "data_dir", "db_path",
    "import_legacy_echidna", "load_vaults", "save_vaults",
]
