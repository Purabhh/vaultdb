"""Retrieval eval: recall@k and MRR for each indexing configuration on the labeled query set.

    uv run python -m vaultdb.eval.retrieval --vault-path ~/Desktop/Claude/Components --split heldout
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import httpx

from ..config import BASELINE, IndexOptions
from ..embedder import DEFAULT_URL, Embedder
from ..search import search
from ..service import VaultService
from ..store import Store

QUERIES = Path(__file__).with_name("queries.jsonl")
EVAL_VAULT = "eval"

CONFIGS: list[tuple[str, IndexOptions]] = [
    ("1 baseline", BASELINE),
    ("2 +prefixes", IndexOptions(keep_code=False, use_prefixes=True, component_cards=False, hybrid=False)),
    ("3 +component cards", IndexOptions(keep_code=True, use_prefixes=True, component_cards=True, hybrid=False)),
    ("4 +hybrid", IndexOptions()),
]


def load_queries(split: str = "heldout") -> list[dict]:
    rows = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows if split == "all" else [r for r in rows if r["split"] == split]


def metrics(ranked: list[list[str]], gold: list[set[str]]) -> dict[str, float]:
    n = len(ranked)
    out = {f"recall@{k}": sum(bool(set(r[:k]) & g) for r, g in zip(ranked, gold)) / n for k in (1, 3, 5)}
    rr = []
    for r, g in zip(ranked, gold):
        rank = next((i + 1 for i, p in enumerate(r) if p in g), None)
        rr.append(1 / rank if rank else 0.0)
    out["mrr"] = sum(rr) / n
    return {k: round(v, 4) for k, v in out.items()}


def run_config(name: str, opts: IndexOptions, vault_path: Path, queries: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["VAULTDB_DATA_DIR"] = str(Path(tmp) / "data")
        embedder = Embedder(use_prefixes=opts.use_prefixes)
        svc = VaultService(Store(Path(tmp) / "db.sqlite3"), embedder, opts)
        svc.create_vault(EVAL_VAULT, str(vault_path))
        ranked = []
        for q in queries:
            hits = search(svc.store, embedder, q["q"], vault=EVAL_VAULT, limit=5, opts=opts)
            ranked.append([Path(h.path).relative_to(vault_path).as_posix() for h in hits])
        svc.store.close()
    return {"config": name, **metrics(ranked, [set(q["gold"]) for q in queries]), "ranked": ranked}


def _chat_model_available() -> bool:
    try:
        models = httpx.get(f"{DEFAULT_URL}/api/tags", timeout=3).json().get("models", [])
    except httpx.HTTPError:
        return False
    return any("embed" not in m.get("name", "") for m in models)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault-path", type=Path, required=True)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="heldout")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--with-llm", action="store_true", help="add the optional LLM-description config")
    args = ap.parse_args(argv)
    vault = args.vault_path.expanduser()
    queries = load_queries(args.split)

    results = [run_config(name, opts, vault, queries) for name, opts in CONFIGS]
    if args.with_llm:
        if _chat_model_available():
            print("note: LLM descriptions are not implemented in this build; config 5 skipped")
        else:
            print("skip: config 5 needs a local Ollama chat model (none installed)")

    print(f"\nsplit={args.split}  queries={len(queries)}  vault={vault}")
    print(f"{'config':<22}{'R@1':>8}{'R@3':>8}{'R@5':>8}{'MRR':>8}")
    for r in results:
        print(f"{r['config']:<22}{r['recall@1']:>8.3f}{r['recall@3']:>8.3f}{r['recall@5']:>8.3f}{r['mrr']:>8.3f}")
    if args.json:
        args.json.write_text(json.dumps({"split": args.split, "queries": queries, "results": results}, indent=2))


if __name__ == "__main__":
    main()
