"""The index: one SQLite file (WAL) holding notes, chunks, an FTS5 keyword index and vectors.

The desktop app and the MCP server open the same file from separate processes; WAL
allows one writer alongside any number of readers.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np

from .chunker import IndexDoc
from .components import ComponentInfo
from .markdown import ParsedNote

DIM = 768

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    vault TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    mtime REAL NOT NULL,
    is_component INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    links TEXT NOT NULL DEFAULT '[]',
    dependencies TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    UNIQUE (vault, path)
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_note ON chunks(note_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

_NOTE_COLS = "n.path, n.title, n.vault, n.is_component, n.category, n.tags, n.links, n.dependencies, n.source"


def _note_dict(row: tuple) -> dict:
    path, title, vault, is_comp, category, tags, links, deps, source = row
    return {
        "path": path, "title": title, "vault": vault, "is_component": bool(is_comp),
        "category": category, "tags": json.loads(tags), "links": json.loads(links),
        "dependencies": json.loads(deps), "source": source,
    }


def _in(kinds: set[str]) -> tuple[str, list[str]]:
    ks = sorted(kinds)
    return ",".join("?" * len(ks)), ks


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        self.conn.execute("PRAGMA busy_timeout=5000")
        # Switching a fresh file to WAL, and creating the schema, can fail at once with "database
        # is locked" when another connection (the MCP's refresh thread, the app) is doing the same;
        # the busy timeout does not cover the WAL switch. Retry both briefly.
        self._retry_locked(self._enable_wal)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._retry_locked(lambda: self.conn.executescript(f"BEGIN IMMEDIATE;\n{_SCHEMA}\nCOMMIT;"))

    def _enable_wal(self) -> None:
        if self.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            self.conn.execute("PRAGMA journal_mode=WAL")

    def _retry_locked(self, fn, attempts: int = 100, delay: float = 0.05) -> None:
        for attempt in range(attempts):
            try:
                fn()
                return
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) and "busy" not in str(e):
                    raise
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                if attempt == attempts - 1:
                    raise
                time.sleep(delay)

    # --- writes ------------------------------------------------------------------------
    def upsert_note(self, vault: str, note: ParsedNote, component: ComponentInfo | None,
                    mtime: float, docs: list[IndexDoc], vectors: np.ndarray) -> int:
        if len(docs) != len(vectors):
            raise ValueError(f"{len(docs)} docs but {len(vectors)} vectors")
        tags = component.tags if component else note.tags
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                note_id = self.conn.execute(
                    """INSERT INTO notes (vault, path, title, mtime, is_component, category, tags, links, dependencies, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(vault, path) DO UPDATE SET title=excluded.title, mtime=excluded.mtime,
                         is_component=excluded.is_component, category=excluded.category, tags=excluded.tags,
                         links=excluded.links, dependencies=excluded.dependencies, source=excluded.source
                       RETURNING id""",
                    (vault, note.path, component.name if component else note.title, mtime,
                     int(component is not None), component.category if component else "",
                     json.dumps(tags), json.dumps(note.links),
                     json.dumps(component.dependencies if component else []),
                     component.source if component else ""),
                ).fetchone()[0]
                self.conn.execute("DELETE FROM chunks WHERE note_id = ?", (note_id,))
                self.conn.executemany(
                    "INSERT INTO chunks (note_id, kind, idx, text, embedding) VALUES (?, ?, ?, ?, ?)",
                    [(note_id, d.kind, d.idx, d.text, np.asarray(v, dtype=np.float32).tobytes())
                     for d, v in zip(docs, vectors)],
                )
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        return note_id

    def delete_note(self, vault: str, path: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM notes WHERE vault = ? AND path = ?", (vault, path))

    def delete_vault(self, vault: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM notes WHERE vault = ?", (vault,))

    def rename_path(self, vault: str, old: str, new: str) -> None:
        """Rename a note, or a folder (every note under it)."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "UPDATE notes SET path = ?, title = ? WHERE vault = ? AND path = ? AND is_component = 0",
                    (new, Path(new).stem, vault, old))
                self.conn.execute("UPDATE notes SET path = ? WHERE vault = ? AND path = ?", (new, vault, old))
                for sep in ("/", "\\"):
                    prefix = old.rstrip("/\\") + sep
                    rows = self.conn.execute(
                        "SELECT id, path FROM notes WHERE vault = ? AND substr(path, 1, ?) = ?",
                        (vault, len(prefix), prefix)).fetchall()
                    for nid, p in rows:
                        self.conn.execute("UPDATE notes SET path = ? WHERE id = ?",
                                          (new.rstrip("/\\") + sep + p[len(prefix):], nid))
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    # --- reads -------------------------------------------------------------------------
    def note_mtimes(self, vault: str) -> dict[str, float]:
        return dict(self.conn.execute("SELECT path, mtime FROM notes WHERE vault = ?", (vault,)).fetchall())

    def notes(self, vault: str | None = None) -> list[dict]:
        sql = f"SELECT {_NOTE_COLS} FROM notes n"
        rows = (self.conn.execute(sql + " WHERE n.vault = ? ORDER BY n.path", (vault,)) if vault is not None
                else self.conn.execute(sql + " ORDER BY n.vault, n.path"))
        return [_note_dict(r) for r in rows.fetchall()]

    def chunks_for_note(self, vault: str, path: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT c.kind, c.idx, c.text, c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id
               WHERE n.vault = ? AND n.path = ? ORDER BY c.kind, c.idx""", (vault, path)).fetchall()
        return [{"kind": k, "idx": i, "text": t, "embedding": np.frombuffer(e, dtype=np.float32)}
                for k, i, t, e in rows]

    def vector_matrix(self, vault: str | None, kinds: set[str]) -> tuple[np.ndarray, list[int]]:
        marks, ks = _in(kinds)
        sql = f"SELECT c.id, c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id WHERE c.kind IN ({marks})"
        args: list = list(ks)
        if vault is not None:
            sql += " AND n.vault = ?"
            args.append(vault)
        rows = self.conn.execute(sql, args).fetchall()
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32), []
        ids = [r[0] for r in rows]
        return np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows]), ids

    def fts_search(self, query: str, vault: str | None, kinds: set[str], limit: int) -> list[tuple[int, float]]:
        terms = re.findall(r"\w+", query)
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        marks, ks = _in(kinds)
        sql = f"""SELECT c.id, bm25(chunks_fts) FROM chunks_fts
                  JOIN chunks c ON c.id = chunks_fts.rowid JOIN notes n ON n.id = c.note_id
                  WHERE chunks_fts MATCH ? AND c.kind IN ({marks})"""
        args: list = [match, *ks]
        if vault is not None:
            sql += " AND n.vault = ?"
            args.append(vault)
        sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
        args.append(limit)
        return [(cid, -score) for cid, score in self.conn.execute(sql, args).fetchall()]

    def chunk_meta(self, chunk_ids: list[int]) -> dict[int, dict]:
        if not chunk_ids:
            return {}
        marks = ",".join("?" * len(chunk_ids))
        rows = self.conn.execute(
            f"""SELECT c.id, c.kind, c.idx, c.text, {_NOTE_COLS} FROM chunks c JOIN notes n ON n.id = c.note_id
                WHERE c.id IN ({marks})""", chunk_ids).fetchall()
        out = {}
        for cid, kind, idx, text, *note in rows:
            out[cid] = {"chunk_id": cid, "kind": kind, "idx": idx, "text": text, **_note_dict(tuple(note))}
        return out

    def close(self) -> None:
        self.conn.close()
