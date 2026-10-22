from pathlib import Path

from vaultdb.components import code_signature, parse_component
from vaultdb.markdown import parse_markdown_file


def _component(vault: Path, rel: str):
    return parse_component(parse_markdown_file(vault / rel), vault)


def test_liquid_glass_button_parsed(fixture_vault: Path) -> None:
    c = _component(fixture_vault, "Buttons/liquid-glass-button.md")
    assert c.name == "Liquid Glass Button" and c.category == "Buttons"
    assert c.source == "21st.dev / aliimam"
    assert "glass" in c.tags and "@radix-ui/react-slot" in c.dependencies
    assert c.language == "tsx" and "liquidbuttonVariants" in c.code
    assert "LiquidButton" in c.exports
    assert "@radix-ui/react-slot" in c.imports
    assert {"svg-filter", "backdrop-filter"} <= set(c.techniques)


def test_dependencies_with_parenthesised_lists(fixture_vault: Path) -> None:
    c = _component(fixture_vault, "Forms/animated-ai-input.md")
    assert "shadcn (textarea, button, dropdown-menu)" in c.dependencies
    assert "tailwind" in c.dependencies


def test_plain_note_is_not_a_component(fixture_vault: Path) -> None:
    assert _component(fixture_vault, "Notes/alpha.md") is None


def test_moc_is_not_a_component(fixture_vault: Path) -> None:
    assert _component(fixture_vault, "Components-MOC.md") is None


def test_note_at_vault_root_has_empty_category(tmp_path: Path) -> None:
    p = tmp_path / "solo.md"
    p.write_text("# Solo\n**Tags:** a, b\n\n## Code\n\n```tsx\nexport function Solo() {}\n```\n", encoding="utf-8")
    c = parse_component(parse_markdown_file(p), tmp_path)
    assert c.category == "" and c.tags == ["a", "b"] and c.exports == ["Solo"]


def test_signature_detects_framer_motion() -> None:
    sig = code_signature('import { motion } from "framer-motion"\nexport function Card(props: CardProps) {}\ninterface CardProps { a: string }')
    assert "framer-motion" in sig["imports"] and "Card" in sig["exports"] and "CardProps" in sig["props"]
    assert "animation" in sig["techniques"]


def test_signature_gsap_counts_as_animation() -> None:
    assert "animation" in code_signature('import gsap from "gsap"')["techniques"]


def test_signature_export_list() -> None:
    sig = code_signature("const A = 1\nfunction B() {}\nexport { A, B as Bee }")
    assert {"A", "B"} <= set(sig["exports"])
