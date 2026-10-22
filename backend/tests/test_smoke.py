from pathlib import Path


def test_fixture_vault_has_component_and_plain_notes(fixture_vault: Path) -> None:
    assert (fixture_vault / "Buttons/liquid-glass-button.md").is_file()
    assert (fixture_vault / "Notes/alpha.md").is_file()
