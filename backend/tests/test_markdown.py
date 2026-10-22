import json
from pathlib import Path

from vaultdb.markdown import parse_markdown_file, read_note_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parity_with_rust_snapshots(fixture_vault: Path) -> None:
    snaps = json.loads((FIXTURES / "rust_snapshots.json").read_text(encoding="utf-8"))
    assert len(snaps) >= 15
    for rel, exp in snaps.items():
        note = parse_markdown_file(fixture_vault / rel)
        assert note.title == exp["title"], rel
        assert note.links == exp["links"], rel
        assert note.tags == exp["tags"], rel
        assert note.frontmatter == exp["frontmatter"], rel


def test_code_blocks_are_kept(fixture_vault: Path) -> None:  # intentional difference from Rust
    note = parse_markdown_file(fixture_vault / "Buttons/liquid-glass-button.md")
    assert note.code_blocks and note.code_blocks[0][0] == "tsx"
    assert "liquidbuttonVariants" in note.code_blocks[0][1]
    assert "liquidbuttonVariants" not in note.prose


def test_alias_link_and_inline_tag(fixture_vault: Path) -> None:
    note = parse_markdown_file(fixture_vault / "Notes/alpha.md")
    assert note.links == ["beta", "gamma"]
    assert note.tags == ["design", "idea", "ui"]
    assert note.frontmatter["status"] == "draft"


def test_prose_is_flattened_markdown(fixture_vault: Path) -> None:
    note = parse_markdown_file(fixture_vault / "Notes/alpha.md")
    assert "Alpha is about layout ideas" in note.prose
    assert "Gamma alias" in note.prose
    assert "[[" not in note.prose and "#" not in note.prose.split()[0]
    assert "layoutGrid" not in note.prose


def test_bom_and_bad_bytes_do_not_crash(fixture_vault: Path) -> None:
    gamma = parse_markdown_file(fixture_vault / "Notes/gamma.md")
    assert gamma.title == "gamma" and not gamma.content.startswith("﻿")
    assert "�" in parse_markdown_file(fixture_vault / "Notes/latin1.md").content


def test_read_note_text_strips_bom(fixture_vault: Path) -> None:
    assert read_note_text(fixture_vault / "Notes/gamma.md").startswith("# Gamma")


def test_empty_note(fixture_vault: Path) -> None:
    note = parse_markdown_file(fixture_vault / "Notes/empty.md")
    assert note.prose == "" and note.code_blocks == [] and note.links == []


def test_unclosed_fence_treats_rest_as_code(tmp_path: Path) -> None:
    p = tmp_path / "open.md"
    p.write_text("intro\n```js\nconst a = 1\n", encoding="utf-8")
    note = parse_markdown_file(p)
    assert note.code_blocks == [("js", "const a = 1")]
    assert note.prose == "intro"
