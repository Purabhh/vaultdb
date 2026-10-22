"""Score agent-eval runs: did the output reuse the expected component, how faithfully, does it build?

    uv run python -m vaultdb.eval.agent.score runs/ --vault-path ~/Desktop/Claude/Components
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fingerprints import fingerprints
from .run import load_tasks

SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".css"}
MIN_HITS = 2


def _output_text(project: Path) -> str:
    src = project / "src"
    if not src.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in sorted(src.rglob("*")) if p.suffix in SOURCE_SUFFIXES and p.is_file())


def score_task(output: str, expected: list[str], vault_path: Path) -> tuple[bool, float]:
    adopted, fidelity = False, 0.0
    output = " ".join(output.split())  # fingerprints store class strings with single spaces
    for rel in expected:
        path = vault_path / rel
        if not path.is_file():
            continue
        fp = fingerprints(path.read_text(encoding="utf-8", errors="replace"))
        if not fp:
            continue
        hits = sum(1 for f in fp if f in output)
        adopted = adopted or hits >= min(MIN_HITS, len(fp))
        fidelity = max(fidelity, hits / len(fp))
    return adopted, fidelity


def score_runs(runs_root: Path, tasks: list[dict], vault_path: Path) -> dict[str, dict]:
    report: dict[str, dict] = {}
    for arm_dir in sorted(p for p in Path(runs_root).iterdir() if p.is_dir()):
        rows = []
        for task in tasks:
            run = arm_dir / task["id"]
            if not run.is_dir():
                continue
            adopted, fidelity = score_task(_output_text(run / "project"), task["expected"], vault_path)
            result = json.loads((run / "result.json").read_text()) if (run / "result.json").is_file() else {}
            rows.append((adopted, fidelity, bool(result.get("build_ok"))))
        if rows:
            n = len(rows)
            report[arm_dir.name] = {
                "n": n,
                "adoption": round(sum(r[0] for r in rows) / n, 4),
                "fidelity": round(sum(r[1] for r in rows) / n, 4),
                "build": round(sum(r[2] for r in rows) / n, 4),
            }
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path)
    ap.add_argument("--vault-path", type=Path, required=True)
    args = ap.parse_args(argv)
    report = score_runs(args.runs, load_tasks(), args.vault_path.expanduser())
    print(f"{'arm':<8}{'tasks':>7}{'adoption':>10}{'fidelity':>10}{'build':>8}")
    for arm, r in report.items():
        print(f"{arm:<8}{r['n']:>7}{r['adoption']:>10.0%}{r['fidelity']:>10.0%}{r['build']:>8.0%}")


if __name__ == "__main__":
    main()
