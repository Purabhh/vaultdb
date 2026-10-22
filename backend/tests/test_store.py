import multiprocessing as mp
import sqlite3
import time
from pathlib import Path

import numpy as np

from vaultdb.chunker import IndexDoc
from vaultdb.components import ComponentInfo
from vaultdb.markdown import ParsedNote
from vaultdb.store import Store

DIM = 768


def _vecs(n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal((n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _note(path: str, title: str = "Glass Button") -> ParsedNote:
    return ParsedNote(title=title, path=path, content="", links=["other"], tags=["ui"])


def _component() -> ComponentInfo:
    return ComponentInfo(name="Glass Button", category="Buttons", source="21st.dev / x",
                         tags=["glass"], dependencies=["tailwind"])


def make_store_with_one_note(tmp_path: Path) -> Store:
    s = Store(tmp_path / "db.sqlite3")
    docs = [IndexDoc("card", 0, "Glass Button frosted LiquidButton"), IndexDoc("code", 0, "const liquidbuttonVariants = cva()")]
    s.upsert_note("V", _note("/v/Buttons/glass.md"), _component(), 1.0, docs, _vecs(2))
    return s


def test_wal_mode_enabled(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    assert s.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_notes_and_mtimes(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    [n] = s.notes("V")
    assert n["path"] == "/v/Buttons/glass.md" and n["is_component"] and n["category"] == "Buttons"
    assert n["tags"] == ["glass"] and n["dependencies"] == ["tailwind"] and n["links"] == ["other"]
    assert s.note_mtimes("V") == {"/v/Buttons/glass.md": 1.0}
    assert s.notes("Other") == []


def test_upsert_replaces_previous_chunks(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    s.upsert_note("V", _note("/v/Buttons/glass.md"), None, 2.0, [IndexDoc("prose", 0, "new text")], _vecs(1, 1))
    chunks = s.chunks_for_note("V", "/v/Buttons/glass.md")
    assert [c["text"] for c in chunks] == ["new text"] and chunks[0]["embedding"].shape == (DIM,)
    assert s.note_mtimes("V")["/v/Buttons/glass.md"] == 2.0
    assert len(s.notes("V")) == 1 and not s.notes("V")[0]["is_component"]


def test_delete_note_cascades_and_clears_fts(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    assert s.fts_search("LiquidButton", None, {"card"}, 5)
    s.delete_note("V", "/v/Buttons/glass.md")
    assert s.fts_search("LiquidButton", None, {"card", "code", "prose"}, 5) == []
    assert s.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def test_delete_vault_removes_only_that_vault(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    s.upsert_note("W", _note("/w/a.md", "A"), None, 1.0, [IndexDoc("prose", 0, "a")], _vecs(1))
    s.delete_vault("V")
    assert s.notes("V") == [] and len(s.notes("W")) == 1


def test_rename_path_moves_note_and_folder_children(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    s.rename_path("V", "/v/Buttons/glass.md", "/v/Buttons/frosted.md")
    comp = s.notes("V")[0]
    assert comp["path"] == "/v/Buttons/frosted.md" and comp["title"] == "Glass Button"  # heading-derived
    s.upsert_note("V", _note("/v/notes/plain.md", "plain"), None, 1.0, [IndexDoc("prose", 0, "p")], _vecs(1))
    s.rename_path("V", "/v/notes/plain.md", "/v/notes/renamed.md")
    assert {n["path"]: n["title"] for n in s.notes("V")}["/v/notes/renamed.md"] == "renamed"
    s.rename_path("V", "/v/Buttons", "/v/Btns")
    assert "/v/Btns/frosted.md" in s.note_mtimes("V")


def test_vector_matrix_filters_by_kind_and_vault(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    s.upsert_note("W", _note("/w/a.md", "A"), None, 1.0, [IndexDoc("prose", 0, "a")], _vecs(1, 5))
    m, ids = s.vector_matrix("V", {"card"})
    assert m.shape == (1, DIM) and len(ids) == 1
    m, ids = s.vector_matrix(None, {"card", "code", "prose"})
    assert m.shape == (3, DIM)
    m, ids = s.vector_matrix("Nope", {"card"})
    assert m.shape == (0, DIM) and ids == []


def test_chunk_meta_joins_note_fields(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    [(cid, _)] = s.fts_search("liquidbuttonVariants", "V", {"code"}, 5)
    meta = s.chunk_meta([cid])[cid]
    assert meta["kind"] == "code" and meta["title"] == "Glass Button" and meta["vault"] == "V"
    assert meta["category"] == "Buttons" and meta["is_component"]


def test_fts_query_with_punctuation_does_not_error(tmp_path: Path) -> None:
    s = make_store_with_one_note(tmp_path)
    assert s.fts_search('glass "button" (AND) -*', None, {"card"}, 5)
    assert s.fts_search("!!!", None, {"card"}, 5) == []


def _writer(db: str, seconds: float, q: "mp.Queue") -> None:
    try:
        s = Store(Path(db))
        end = time.time() + seconds
        i = 0
        while time.time() < end:
            s.upsert_note("V", _note("/v/x.md", "X"), None, float(i), [IndexDoc("prose", 0, f"text {i}")], _vecs(1, i))
            i += 1
        q.put(("writer", i))
    except Exception as e:  # pragma: no cover - reported to the parent
        q.put(("error", repr(e)))


def _reader(db: str, seconds: float, q: "mp.Queue") -> None:
    try:
        s = Store(Path(db))
        end = time.time() + seconds
        n = 0
        while time.time() < end:
            m, ids = s.vector_matrix(None, {"prose"})
            assert m.shape[0] == len(ids)
            s.fts_search("text", None, {"prose"}, 5)
            n += 1
        q.put(("reader", n))
    except Exception as e:  # pragma: no cover
        q.put(("error", repr(e)))


def test_concurrent_writer_and_reader(tmp_path: Path) -> None:
    db = str(tmp_path / "db.sqlite3")
    Store(Path(db))  # create schema first
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_writer, args=(db, 3.0, q)), ctx.Process(target=_reader, args=(db, 3.0, q))]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    results = [q.get(timeout=5) for _ in procs]
    assert not [r for r in results if r[0] == "error"], results
    assert all(r[1] > 0 for r in results)
    assert sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
