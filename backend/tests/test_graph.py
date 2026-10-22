from pathlib import Path

import pytest

from conftest import index_fixture
from vaultdb.graph import SEMANTIC_THRESHOLD, build_graph
from vaultdb.store import Store


def _graph(tmp_path: Path, root: Path, embedder) -> dict:
    store = Store(tmp_path / "db.sqlite3")
    index_fixture(store, embedder, root, vault="V")
    return build_graph(store, "V")


def _edges(g: dict, kind: str) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in g["edges"] if e["edge_type"] == kind}


def test_shape(tmp_path, fixture_vault, fake_embedder) -> None:
    g = _graph(tmp_path, fixture_vault, fake_embedder)
    node = next(n for n in g["nodes"] if n["id"] == "alpha")
    assert set(node) == {"id", "title", "path", "tags", "link_count"}
    assert node["link_count"] == 2 and node["path"].endswith("alpha.md")
    assert all(set(e) == {"source", "target", "edge_type", "weight"} for e in g["edges"])


def test_link_and_backlink_edges(tmp_path, fixture_vault, fake_embedder) -> None:
    g = _graph(tmp_path, fixture_vault, fake_embedder)
    assert {("alpha", "beta"), ("alpha", "gamma")} <= _edges(g, "link")
    assert ("gamma", "alpha") in _edges(g, "backlink")


def test_unresolved_link_becomes_ghost_and_anchors_are_stripped(tmp_path, fake_embedder) -> None:
    root = tmp_path / "v"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("# A\nsee [[sub/B#Heading]] and [[missing]]\n", encoding="utf-8")
    (root / "sub" / "B.md").write_text("# B\n", encoding="utf-8")
    g = _graph(tmp_path, root, fake_embedder)
    assert ("a", "B") in _edges(g, "link")
    ghost = next(n for n in g["nodes"] if n["id"] == "missing")
    assert ghost["path"] == "" and ghost["link_count"] == 0


def test_no_self_or_duplicate_edges(tmp_path, fake_embedder) -> None:
    root = tmp_path / "v"
    root.mkdir()
    (root / "a.md").write_text("[[a]] [[b]] [[b]] [[B]]\n", encoding="utf-8")
    (root / "b.md").write_text("[[a]]\n", encoding="utf-8")
    g = _graph(tmp_path, root, fake_embedder)
    pairs = [(e["source"], e["target"]) for e in g["edges"] if e["edge_type"] in ("link", "backlink")]
    assert len(pairs) == len(set(pairs)) and ("a", "a") not in pairs


def test_shared_tags_make_tag_edges(tmp_path, fake_embedder) -> None:
    root = tmp_path / "v"
    root.mkdir()
    for name in ("x", "y"):
        (root / f"{name}.md").write_text(f"# {name}\n#shared\n", encoding="utf-8")
    g = _graph(tmp_path, root, fake_embedder)
    assert _edges(g, "tag") & {("x", "y"), ("y", "x")}


def test_semantic_edges_respect_threshold(tmp_path, fake_embedder) -> None:
    root = tmp_path / "v"
    root.mkdir()
    (root / "one.md").write_text("aurora borealis polar lights night sky\n", encoding="utf-8")
    (root / "two.md").write_text("aurora borealis polar lights night sky\n", encoding="utf-8")
    (root / "far.md").write_text("tax spreadsheet quarterly invoices\n", encoding="utf-8")
    g = _graph(tmp_path, root, fake_embedder)
    sem = {frozenset((e["source"], e["target"])): e["weight"] for e in g["edges"] if e["edge_type"] == "semantic"}
    assert sem[frozenset(("one", "two"))] == pytest.approx(1.0, abs=1e-5)
    assert frozenset(("one", "far")) not in sem
    assert all(w > SEMANTIC_THRESHOLD for w in sem.values())


def test_service_get_graph(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    from vaultdb.service import VaultService
    svc = VaultService(Store(tmp_path / "db2.sqlite3"), fake_embedder)
    svc.create_vault("V", str(fixture_vault))
    assert any(n["id"] == "alpha" for n in svc.get_graph("V")["nodes"])
