"""Note graph: wikilink, backlink, shared-tag and semantic edges (port of the Rust build_graph)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .store import Store

SEMANTIC_THRESHOLD = 0.55
MAX_TAG_GROUP = 20  # tags on more notes than this are too common to draw


def build_graph(store: Store, vault: str) -> dict:
    nodes: dict[str, dict] = {}
    pending: list[tuple[str, list[str]]] = []
    path_to_id: dict[str, str] = {}

    for n in store.notes(vault):
        node_id = Path(n["path"]).stem
        path_to_id[n["path"]] = node_id
        node = nodes.setdefault(node_id, {"id": node_id, "title": node_id, "path": n["path"],
                                          "tags": n["tags"], "link_count": 0})
        node["link_count"] = len(n["links"])
        if n["links"]:
            pending.append((node_id, n["links"]))

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    lower = {t.lower(): t for t in nodes}

    def add(source: str, target: str, kind: str, weight: float) -> None:
        if (source, target) not in seen:
            seen.add((source, target))
            edges.append({"source": source, "target": target, "edge_type": kind, "weight": weight})

    for source, links in pending:
        for link in links:
            no_anchor = link.split("#", 1)[0]
            name = no_anchor.rsplit("/", 1)[-1]
            if not name:
                continue
            target = name if name in nodes else no_anchor if no_anchor in nodes else lower.get(name.lower())
            if target is None:
                target = name
                nodes.setdefault(name, {"id": name, "title": name, "path": "", "tags": [], "link_count": 0})
                lower.setdefault(name.lower(), name)
            if target != source:
                add(source, target, "link", 1.0)
                add(target, source, "backlink", 0.8)

    by_tag: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        for tag in node["tags"]:
            by_tag.setdefault(tag, []).append(node_id)
    for members in by_tag.values():
        if 2 <= len(members) <= MAX_TAG_GROUP:
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    add(members[i], members[j], "tag", 0.5)

    matrix, ids = store.vector_matrix(vault, {"card", "prose"})
    if ids:
        meta = store.chunk_meta(ids)
        grouped: dict[str, list[int]] = {}
        for row, cid in enumerate(ids):
            node_id = path_to_id.get(meta[cid]["path"])
            if node_id is not None:
                grouped.setdefault(node_id, []).append(row)
        names = sorted(grouped)
        means = np.vstack([matrix[grouped[n]].mean(axis=0) for n in names])
        norms = np.linalg.norm(means, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        means = means / norms
        sims = means @ means.T
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if sims[i, j] > SEMANTIC_THRESHOLD:
                    edges.append({"source": names[i], "target": names[j], "edge_type": "semantic",
                                  "weight": float(sims[i, j])})

    return {"nodes": list(nodes.values()), "edges": edges}
