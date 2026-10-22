from pathlib import Path

import pytest

from conftest import index_fixture
from vaultdb.config import IndexOptions
from vaultdb.search import rrf, search
from vaultdb.store import Store


@pytest.fixture
def indexed(tmp_path: Path, fixture_vault: Path, fake_embedder):
    store = Store(tmp_path / "db.sqlite3")
    index_fixture(store, fake_embedder, fixture_vault)
    return store


def test_rrf_orders_by_combined_rank() -> None:
    ranked = rrf([[1, 2, 3], [3, 1]])
    assert [c for c, _ in ranked][:2] == [1, 3]
    assert ranked[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_one_hit_per_note(indexed, fake_embedder) -> None:
    hits = search(indexed, fake_embedder, "button glass hover", vault="Components", limit=20, opts=IndexOptions())
    paths = [h.path for h in hits]
    assert len(paths) == len(set(paths))


def test_keyword_finds_component_by_code_identifier(indexed, fake_embedder) -> None:
    hits = search(indexed, fake_embedder, "LiquidButton", vault="Components", limit=3,
                  opts=IndexOptions(), components_only=True)
    assert hits[0].title == "Liquid Glass Button"
    assert hits[0].is_component and hits[0].category == "Buttons"
    assert "@radix-ui/react-slot" in hits[0].dependencies


def test_components_only_excludes_plain_notes(indexed, fake_embedder) -> None:
    hits = search(indexed, fake_embedder, "layout grid spacing", vault="Components", limit=20,
                  opts=IndexOptions(), components_only=True)
    assert hits and all(h.is_component for h in hits)
    everything = search(indexed, fake_embedder, "layout grid spacing", vault="Components", limit=20, opts=IndexOptions())
    assert any(h.path.endswith("alpha.md") for h in everything)


def test_score_is_cosine_between_zero_and_one(indexed, fake_embedder) -> None:
    hits = search(indexed, fake_embedder, "glass button", vault="Components", limit=5, opts=IndexOptions())
    assert all(0.0 <= h.score <= 1.0 + 1e-6 for h in hits)


def test_vector_only_when_hybrid_off(indexed, fake_embedder, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(indexed, "fts_search", lambda *a, **k: called.append(1) or [])
    hits = search(indexed, fake_embedder, "glass button", vault="Components", limit=5,
                  opts=IndexOptions(hybrid=False))
    assert hits and called == []
    assert [h.score for h in hits] == sorted([h.score for h in hits], reverse=True)


def test_unknown_vault_returns_nothing(indexed, fake_embedder) -> None:
    assert search(indexed, fake_embedder, "glass", vault="Nope", limit=5, opts=IndexOptions()) == []


def test_empty_query_raises_value_error(indexed, fake_embedder) -> None:
    with pytest.raises(ValueError):
        search(indexed, fake_embedder, "   ", vault=None, limit=5, opts=IndexOptions())
