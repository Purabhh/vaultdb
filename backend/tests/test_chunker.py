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


def test_dense_code_is_capped_by_characters() -> None:
    # 60 lines of ~300-char class strings: few lines, but far over the model's 2,048-token context
    line = 'const c = "' + "px-4 py-2 rounded-md shadow-[0_0_6px_rgba(0,0,0,0.03)] " * 5 + '"'
    parts = chunk_code("export function Dense() {\n" + "\n".join([line] * 60) + "\n}\n")
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)


def test_single_huge_line_is_split() -> None:
    parts = chunk_code("const x = '" + "a" * 10000 + "'")
    assert all(len(p) <= 4000 for p in parts) and sum(len(p) for p in parts) >= 10000


def test_card_stays_within_size_cap_for_long_usage_notes(tmp_path: Path) -> None:
    p = tmp_path / "Big" / "big.md"
    p.parent.mkdir()
    p.write_text("# Big\n**Tags:** a\n\n## Code\n\n```tsx\nexport function Big() {}\n```\n\n## Usage Notes\n\n"
                 + "word " * 3000, encoding="utf-8")
    note = parse_markdown_file(p)
    docs = build_index_docs(note, parse_component(note, tmp_path), IndexOptions())
    assert all(len(d.text) <= 4000 for d in docs)
    assert any(d.kind == "prose" for d in docs)  # the long notes are still indexed, as prose chunks


def test_empty_note_has_no_docs(fixture_vault: Path) -> None:
    assert _docs(fixture_vault, "Notes/empty.md", IndexOptions()) == []


def test_prose_chunks_are_capped_by_characters() -> None:
    # no spaces at all (e.g. a long URL or CJK text) must still be split
    chunks = chunk_prose("x" * 20000)
    assert len(chunks) > 1 and all(len(c) <= 3000 for c in chunks)


def test_code_and_cards_fit_a_token_safe_cap(fixture_vault: Path) -> None:
    line = 'const p = "M10 20 L30 40 C50 60 70 80 90 100 Z M1 2 L3 4" ' * 3
    parts = chunk_code("\n".join([line] * 80))
    assert all(len(p) <= 3000 for p in parts)
