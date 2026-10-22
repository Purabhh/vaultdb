"""Shared fixtures: a temp copy of the fixture vault, a temp data dir, a fake embedder."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import httpx
import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
OLLAMA_URL = "http://localhost:11434"


@pytest.fixture
def fixture_vault(tmp_path: Path) -> Path:
    """A throwaway copy of tests/fixtures/vault, safe to edit."""
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURES / "vault", dst)
    return dst


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points vaultdb's data directory at a temp folder (via VAULTDB_DATA_DIR)."""
    d = tmp_path / "base" / "vaultdb"
    d.mkdir(parents=True)
    monkeypatch.setenv("VAULTDB_DATA_DIR", str(d))
    return d


class FakeEmbedder:
    """Deterministic stand-in for Embedder: hashed bag-of-words, L2-normalised.

    Texts that share words get similar vectors, so search tests behave sensibly
    without Ollama. Records every call.
    """

    dim = 768

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in text.lower().split():
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.calls.append(("documents", list(texts)))
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._vec(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        self.calls.append(("query", text))
        return self._vec(text)


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


_ollama_up: bool | None = None


def _ollama_reachable() -> bool:
    global _ollama_up
    if _ollama_up is None:
        try:
            _ollama_up = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).status_code == 200
        except httpx.HTTPError:
            _ollama_up = False
    return _ollama_up


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if any("ollama" in item.keywords for item in items) and not _ollama_reachable():
        skip = pytest.mark.skip(reason=f"Ollama not reachable at {OLLAMA_URL}")
        for item in items:
            if "ollama" in item.keywords:
                item.add_marker(skip)
