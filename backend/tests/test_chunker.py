from pathlib import Path

from vaultdb.chunker import build_index_docs, chunk_code, chunk_prose
from vaultdb.components import parse_component
from vaultdb.config import BASELINE, IndexOptions
from vaultdb.markdown import parse_markdown_file


def _docs(vault: Path, rel: str, opts: IndexOptions):
    note = parse_markdown_file(vault / rel)
    return build_index_docs(note, parse_component(note, vault), opts)


def test_component_gets_card_and_code_docs(fixture_vault: Path) -> None:
    docs = _docs(fixture_vault, "Buttons/liquid-glass-button.md", IndexOptions())
    card = [d for d in docs if d.kind == "card"]
    assert len(card) == 1 and card[0].idx == 0
    for s in ("Liquid Glass Button", "Buttons", "glass", "LiquidButton", "svg-filter", "@radix-ui/react-slot"):
        assert s in card[0].text
    assert any(d.kind == "code" and "liquidbuttonVariants" in d.text for d in docs)
    assert [d.idx for d in docs if d.kind == "code"] == list(range(sum(d.kind == "code" for d in docs)))


def test_baseline_reproduces_old_behavior(fixture_vault: Path) -> None:
    docs = _docs(fixture_vault, "Buttons/liquid-glass-button.md", BASELINE)
    assert [d.kind for d in docs] == ["prose"]
    assert "liquidbuttonVariants" not in docs[0].text


def test_code_without_cards_indexes_component_like_plain_note(fixture_vault: Path) -> None:
    docs = _docs(fixture_vault, "Buttons/liquid-glass-button.md", IndexOptions(component_cards=False))
    assert {d.kind for d in docs} == {"prose", "code"}


def test_plain_note_keeps_code_as_code_chunk(fixture_vault: Path) -> None:
    docs = _docs(fixture_vault, "Notes/alpha.md", IndexOptions())
    assert {d.kind for d in docs} == {"prose", "code"}
    assert any("layoutGrid" in d.text for d in docs if d.kind == "code")


def test_chunk_prose_matches_rust_algorithm() -> None:
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_prose(words)
    assert len(chunks) == 3 and chunks[1].split()[0] == "w448"
    assert chunk_prose("") == [] and chunk_prose("a b") == ["a b"]


def test_chunk_code_splits_on_top_level_declarations() -> None:
    decl = "export function A() {\n" + "  a();\n" * 100 + "}\n"
    parts = chunk_code(decl + decl.replace(" A(", " B("))
    assert len(parts) == 2 and parts[1].startswith("export function B")


def test_small_declarations_are_merged() -> None:
    code = "\n".join(f"const c{i} = {i}" for i in range(10))
    assert len(chunk_code(code)) == 1


def test_long_declaration_is_hard_split() -> None:
    code = "export function Big() {\n" + "  x();\n" * 5000 + "}\n"
    parts = chunk_code(code)
    assert len(parts) >= 40 and all(p.count("\n") <= 120 for p in parts)
    assert "".join(parts).count("x();") == 5000


def test_empty_note_has_no_docs(fixture_vault: Path) -> None:
    assert _docs(fixture_vault, "Notes/empty.md", IndexOptions()) == []
