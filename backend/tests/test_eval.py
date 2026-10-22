import json
from pathlib import Path

import pytest

from vaultdb.eval.retrieval import CONFIGS, load_queries, metrics

REAL_VAULT = Path.home() / "Desktop/Claude/Components"


def test_metrics_known_values() -> None:
    assert metrics([["a", "b"], ["c", "a"]], [{"a"}, {"a"}]) == {
        "recall@1": 0.5, "recall@3": 1.0, "recall@5": 1.0, "mrr": 0.75,
    }


def test_metrics_miss_scores_zero() -> None:
    assert metrics([["x", "y"]], [{"a"}]) == {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0}


def test_queries_file_well_formed() -> None:
    qs = load_queries("all")
    assert len(qs) == 70
    assert {q["split"] for q in qs} == {"dev", "heldout"}
    assert len(load_queries("heldout")) == 35


def test_configs_cover_the_spec_ladder() -> None:
    assert [c[0] for c in CONFIGS] == ["1 baseline", "2 +prefixes", "3 +component cards", "4 +hybrid"]


@pytest.mark.skipif(not REAL_VAULT.is_dir(), reason="real Components vault not on this machine")
def test_every_gold_path_exists_and_no_query_names_its_component() -> None:
    for q in load_queries("all"):
        for gold in q["gold"]:
            path = REAL_VAULT / gold
            assert path.is_file(), gold
            title = path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").split(" (")[0].lower()
            assert title not in q["q"].lower(), (q["q"], title)
