"""Performance: ingest throughput and search latency split into embedding vs store time.

    uv run python -m vaultdb.eval.bench --vault-path ~/Desktop/Claude/Components
"""
from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import time
from pathlib import Path

from ..config import IndexOptions
from ..embedder import Embedder
from ..search import search
from ..service import VaultService, markdown_files
from ..store import Store
from .retrieval import load_queries


class TimedEmbedder:
    def __init__(self, inner: Embedder) -> None:
        self.inner = inner
        self.last_query_ms = 0.0

    def embed_documents(self, texts):
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        t = time.perf_counter()
        v = self.inner.embed_query(text)
        self.last_query_ms = (time.perf_counter() - t) * 1000
        return v


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault-path", type=Path, required=True)
    ap.add_argument("--searches", type=int, default=200)
    args = ap.parse_args(argv)
    vault = args.vault_path.expanduser()
    queries = [q["q"] for q in load_queries("all")]

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["VAULTDB_DATA_DIR"] = str(Path(tmp) / "data")
        emb = TimedEmbedder(Embedder())
        svc = VaultService(Store(Path(tmp) / "db.sqlite3"), emb, IndexOptions())
        n_notes = len(markdown_files(vault))
        t = time.perf_counter()
        svc.create_vault("bench", str(vault))
        ingest_s = time.perf_counter() - t
        chunks = svc.store.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        search(svc.store, emb, "warm up", vault="bench", limit=5, opts=IndexOptions())
        total, embed, store = [], [], []
        for i in range(args.searches):
            q = queries[i % len(queries)]
            t = time.perf_counter()
            search(svc.store, emb, q, vault="bench", limit=5, opts=IndexOptions())
            ms = (time.perf_counter() - t) * 1000
            total.append(ms)
            embed.append(emb.last_query_ms)
            store.append(ms - emb.last_query_ms)
        svc.store.close()

    print(f"vault: {vault}  notes: {n_notes}  chunks: {chunks}")
    print(f"ingest: {ingest_s:.2f} s  ({n_notes / ingest_s:.1f} notes/s, includes embedding)")
    for name, vals in (("search total", total), ("  embedding", embed), ("  store+fusion", store)):
        print(f"{name:<16} p50 {statistics.median(vals):7.1f} ms   p95 {pct(vals, 95):7.1f} ms")


if __name__ == "__main__":
    main()
