"""End-to-end over the fixture vault with the real Ollama embedder."""
from pathlib import Path

import pytest

from vaultdb.embedder import Embedder
from vaultdb.service import VaultService
from vaultdb.store import Store

pytestmark = pytest.mark.ollama


@pytest.fixture(scope="module")
def real_svc(tmp_path_factory, fixture_vault_module):
    import os
    base = tmp_path_factory.mktemp("data")
    os.environ["VAULTDB_DATA_DIR"] = str(base / "vaultdb")
    svc = VaultService(Store(base / "db.sqlite3"), Embedder())
    svc.create_vault("Components", str(fixture_vault_module))
    yield svc
    os.environ.pop("VAULTDB_DATA_DIR", None)


@pytest.fixture(scope="module")
def fixture_vault_module(tmp_path_factory) -> Path:
    import shutil
    dst = tmp_path_factory.mktemp("vault") / "vault"
    shutil.copytree(Path(__file__).parent / "fixtures" / "vault", dst)
    return dst


def _top3(svc, q: str) -> list[str]:
    return [Path(h["path"]).relative_to(svc.vaults["Components"].source_path).as_posix()
            for h in svc.search_vault("Components", q, limit=3)]


def test_frosted_glass_button(real_svc) -> None:
    assert "Buttons/liquid-glass-button.md" in _top3(real_svc, "frosted glass button")


def test_swipeable_card_stack(real_svc) -> None:
    assert "Cards/morphing-card-stack.md" in _top3(real_svc, "swipeable stack of cards")
