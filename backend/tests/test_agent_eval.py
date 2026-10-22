import json
from pathlib import Path

from vaultdb.eval.agent.fingerprints import fingerprints
from vaultdb.eval.agent.run import build_prompt, claude_command, load_tasks
from vaultdb.eval.agent.score import score_runs

FIXTURES = Path(__file__).parent / "fixtures" / "vault"
LIQUID = (FIXTURES / "Buttons/liquid-glass-button.md").read_text(encoding="utf-8")


def test_fingerprints_of_liquid_button() -> None:
    fp = fingerprints(LIQUID)
    assert {"LiquidButton", "liquidbuttonVariants", "GlassFilter"} <= fp
    assert any(f.startswith("shadow-[") for f in fp)
    assert "React" not in fp and "className" not in fp


def test_generic_names_are_not_fingerprints() -> None:
    fp = fingerprints((FIXTURES / "Cards/morphing-card-stack.md").read_text(encoding="utf-8"))
    assert not {"Component", "Cursor", "Tab", "Switch", "App"} & fp


def test_long_class_strings_strengthen_sparse_components() -> None:
    fp = fingerprints((FIXTURES / "Heroes/credit-card-hero.md").read_text(encoding="utf-8"))
    assert len(fp) >= 3
    assert any(" " in f and len(f) >= 40 for f in fp)  # a full className string


def test_tasks_file_is_well_formed() -> None:
    tasks = load_tasks()
    assert len(tasks) == 12 and len({t["id"] for t in tasks}) == 12
    assert all(t["expected"] and t["prompt"] for t in tasks)


def test_prompt_per_arm() -> None:
    task = {"id": "t", "prompt": "a glassy call to action button", "expected": []}
    assert "a glassy call to action button" in build_prompt(task, "none", moc="")
    assert "COMPONENT LIBRARY INDEX" in build_prompt(task, "moc", moc="# Components MOC")
    assert "component library" in build_prompt(task, "mcp", moc="").lower()


def test_claude_command_isolates_mcp_per_arm(tmp_path: Path) -> None:
    none_cmd = claude_command("none", "p", tmp_path / "cfg.json", mcp_bin="/x/vaultdb-mcp")
    mcp_cmd = claude_command("mcp", "p", tmp_path / "cfg.json", mcp_bin="/x/vaultdb-mcp")
    assert "--strict-mcp-config" in none_cmd and "--strict-mcp-config" in mcp_cmd
    assert json.loads((tmp_path / "cfg.json").read_text())["mcpServers"]["vaultdb"]["command"] == "/x/vaultdb-mcp"
    assert "mcp__vaultdb__get_component" in " ".join(mcp_cmd)
    assert "mcp__vaultdb" not in " ".join(none_cmd)


def _fake_run(root: Path, arm: str, task_id: str, source: str, build_ok: bool) -> None:
    d = root / arm / task_id
    (d / "project" / "src").mkdir(parents=True)
    (d / "project" / "src" / "App.tsx").write_text(source, encoding="utf-8")
    (d / "result.json").write_text(json.dumps({"build_ok": build_ok}))


def test_score_counts_adoption_and_fidelity(tmp_path: Path) -> None:
    tasks = [{"id": "glass", "prompt": "", "expected": ["Buttons/liquid-glass-button.md"]}]
    _fake_run(tmp_path, "mcp", "glass", "export function LiquidButton() {}\nconst liquidbuttonVariants = 1\n", True)
    _fake_run(tmp_path, "none", "glass", "export function FancyButton() {}\n", False)
    report = score_runs(tmp_path, tasks, FIXTURES)
    assert report["mcp"]["adoption"] == 1.0 and report["mcp"]["build"] == 1.0
    assert 0 < report["mcp"]["fidelity"] <= 1.0
    assert report["none"]["adoption"] == 0.0 and report["none"]["fidelity"] == 0.0 and report["none"]["build"] == 0.0
