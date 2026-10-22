"""Hybrid search: vector similarity + FTS5 keywords, fused with reciprocal rank fusion."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import IndexOptions
from .store import Store

CANDIDATES = 50  # per ranking, before fusion


@dataclass
class SearchHit:
    title: str
    path: str
    chunk: str
    score: float  # cosine similarity of the best chunk, 0..1 (shown as a percentage in the UI)
    vault: str
    kind: str
    category: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    is_component: bool = False


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def search(store: Store, embedder, query: str, *, vault: str | None, limit: int,
           opts: IndexOptions, components_only: bool = False) -> list[SearchHit]:
    if not query.strip():
        raise ValueError("Search query is empty")
    kinds = {"card", "code"} if components_only else {"card", "code", "prose"}
    matrix, ids = store.vector_matrix(vault, kinds)
    if not ids:
        return []
    qv = embedder.embed_query(query)
    sims = matrix @ np.asarray(qv, dtype=np.float32)
    cosine = dict(zip(ids, sims.tolist()))
    vector_ranking = [ids[i] for i in np.argsort(-sims)]

    if opts.hybrid:
        keyword_ranking = [cid for cid, _ in store.fts_search(query, vault, kinds, CANDIDATES * 4)]
        ordered = [cid for cid, _ in rrf([vector_ranking[:CANDIDATES * 4], keyword_ranking])]
    else:
        ordered = vector_ranking

    hits: list[SearchHit] = []
    seen: set[tuple[str, str]] = set()
    batch = 200
    for start in range(0, len(ordered), batch):
        meta = store.chunk_meta(ordered[start:start + batch])
        for cid in ordered[start:start + batch]:
            m = meta.get(cid)
            if m is None or (components_only and not m["is_component"]):
                continue
            key = (m["vault"], m["path"])
            if key in seen:
                continue
            seen.add(key)
            hits.append(SearchHit(
                title=m["title"], path=m["path"], chunk=m["text"],
                score=float(max(0.0, min(1.0, cosine.get(cid, 0.0)))),
                vault=m["vault"], kind=m["kind"], category=m["category"], tags=m["tags"],
                dependencies=m["dependencies"], is_component=m["is_component"],
            ))
            if len(hits) >= limit:
                return hits
    return hits
