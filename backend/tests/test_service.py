import shutil
from pathlib import Path

import numpy as np
import pytest

from vaultdb.config import load_vaults
from vaultdb.embedder import EmbedderError
from vaultdb.service import VaultError, VaultService
from vaultdb.store import Store


@pytest.fixture
def svc(tmp_path: Path, data_dir: Path, fake_embedder) -> VaultService:
    return VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder)


def _md_count(root: Path) -> int:
    return len(list(root.rglob("*.md")))


def test_create_vault_indexes_all_notes(svc, fixture_vault: Path) -> None:
    info = svc.create_vault("Components", str(fixture_vault))
    assert info == {"name": "Components", "source_path": str(fixture_vault), "note_count": _md_count(fixture_vault)}
    assert load_vaults()["Components"].note_count == _md_count(fixture_vault)
    assert svc.list_vaults() == [info]


def test_duplicate_vault_name_rejected(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    with pytest.raises(VaultError, match="already exists"):
        svc.create_vault("V", str(fixture_vault))


def test_vault_name_with_spaces(svc, fixture_vault: Path) -> None:
    svc.create_vault("My Components", str(fixture_vault))
    hits = svc.search_vault("My Components", "glass button")
    assert hits and set(hits[0]) == {"title", "path", "chunk", "score"}
    svc.delete_vault("My Components")
    assert svc.list_vaults() == [] and svc.store.notes("My Components") == []


def test_search_vault_unknown_vault(svc) -> None:
    with pytest.raises(VaultError, match="not found"):
        svc.search_vault("Nope", "x")


def test_refresh_picks_up_edit_add_delete(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    beta = fixture_vault / "Notes/beta.md"
    beta.write_text("# Beta\n\nNow about zebras.\n", encoding="utf-8")
    import os
    os.utime(beta, (beta.stat().st_atime, beta.stat().st_mtime + 10))
    (fixture_vault / "Notes/new.md").write_text("# New\n\nfresh note\n", encoding="utf-8")
    (fixture_vault / "Notes/gamma.md").unlink()
    assert svc.refresh_vault("V") == {"added": 1, "updated": 1, "removed": 1}
    assert any("zebras" in h["chunk"] for h in svc.search_vault("V", "zebras"))
    assert svc.list_vaults()[0]["note_count"] == _md_count(fixture_vault)


def test_missing_source_folder_is_clear_error(svc, fixture_vault: Path, tmp_path: Path) -> None:
    moved = tmp_path / "moved"
    shutil.copytree(fixture_vault, moved)
    svc.create_vault("V", str(moved))
    shutil.rmtree(moved)
    assert svc.list_vaults()[0]["name"] == "V"
    with pytest.raises(VaultError, match="source folder not found"):
        svc.refresh_vault("V")


def test_path_traversal_rejected(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    with pytest.raises(VaultError, match="outside the vault"):
        svc.save_note("V", str(fixture_vault / ".." / "evil.md"), "x")
    assert not (fixture_vault.parent / "evil.md").exists()


def test_save_note_writes_and_reindexes(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    path = str(fixture_vault / "Notes/beta.md")
    svc.save_note("V", path, "# Beta\n\nAll about walruses now.\n")
    assert "walruses" in Path(path).read_text(encoding="utf-8")
    assert svc.search_vault("V", "walruses")[0]["path"] == path


def test_create_note_and_folder(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    folder = svc.create_folder("V", str(fixture_vault), "Drafts")
    note = svc.create_note("V", folder, "idea")
    assert Path(note).name == "idea.md" and Path(note).read_text(encoding="utf-8") == "# idea\n"
    assert svc.list_vaults()[0]["note_count"] == _md_count(fixture_vault)
    with pytest.raises(VaultError, match="already exists"):
        svc.create_note("V", folder, "idea.md")
    with pytest.raises(VaultError, match="empty"):
        svc.create_folder("V", str(fixture_vault), "  ")


def test_rename_note_updates_index(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    old = str(fixture_vault / "Notes/beta.md")
    new = svc.rename_item("V", old, "beta-renamed.md")
    assert Path(new).exists() and not Path(old).exists()
    paths = {n["path"] for n in svc.store.notes("V")}
    assert new in paths and old not in paths


def test_rename_folder_updates_children(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    new = svc.rename_item("V", str(fixture_vault / "Notes"), "Journal")
    assert str(Path(new) / "alpha.md") in {n["path"] for n in svc.store.notes("V")}


def test_delete_note_and_folder_update_index(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    beta = str(fixture_vault / "Notes/beta.md")
    svc.delete_note("V", beta)
    assert not Path(beta).exists() and beta not in svc.store.note_mtimes("V")
    svc.delete_folder("V", str(fixture_vault / "Notes"))
    assert not any("/Notes/" in p.replace("\\", "/") for p in svc.store.note_mtimes("V"))
    assert svc.list_vaults()[0]["note_count"] == _md_count(fixture_vault)
    with pytest.raises(VaultError, match="vault root"):
        svc.delete_folder("V", str(fixture_vault))


def test_note_detail_shape_and_similar_notes(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    path = str(fixture_vault / "Buttons/liquid-glass-button.md")
    d = svc.get_note_detail("V", path)
    assert set(d) == {"title", "path", "raw_content", "tags", "links", "chunks"}
    assert d["raw_content"] == Path(path).read_text(encoding="utf-8") and d["title"] == "liquid-glass-button"
    assert [c["index"] for c in d["chunks"]] == list(range(len(d["chunks"])))
    sims = [s for c in d["chunks"] for s in c["similar_notes"]]
    assert sims and all(s["title"] != "Liquid Glass Button" for s in sims)
    assert all(len(c["similar_notes"]) <= 5 for c in d["chunks"])


def test_reembed_returns_detail(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    d = svc.reembed_note("V", str(fixture_vault / "Notes/alpha.md"))
    assert d["title"] == "alpha" and d["chunks"]


def test_file_tree_dirs_first_and_md_only(svc, fixture_vault: Path) -> None:
    (fixture_vault / ".obsidian").mkdir()
    (fixture_vault / "image.png").write_bytes(b"x")
    svc.create_vault("V", str(fixture_vault))
    tree = svc.get_file_tree("V")
    names = [c["name"] for c in tree["children"]]
    assert ".obsidian" not in names and "image.png" not in names
    dirs = [c for c in tree["children"] if c["is_dir"]]
    assert tree["children"][: len(dirs)] == dirs and "Components-MOC.md" in names


def test_create_new_vault_makes_empty_folder(svc, tmp_path: Path) -> None:
    info = svc.create_new_vault("Fresh", str(tmp_path))
    assert Path(info["source_path"]).is_dir() and info["note_count"] == 0


def test_delete_vault_keeps_files(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    svc.delete_vault("V")
    assert (fixture_vault / "Notes/alpha.md").exists() and "V" not in load_vaults()


class FailingEmbedder:
    def __init__(self, inner, fail_on: int) -> None:
        self.inner, self.fail_on, self.n = inner, fail_on, 0

    def embed_documents(self, texts):
        self.n += 1
        if self.n == self.fail_on:
            raise EmbedderError("Ollama is not running at http://localhost:11434.")
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def test_embedder_failure_mid_ingest_leaves_no_partial_vault(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    svc = VaultService(Store(tmp_path / "db.sqlite3"), FailingEmbedder(fake_embedder, fail_on=3))
    with pytest.raises(VaultError, match="Ollama"):
        svc.create_vault("V", str(fixture_vault))
    assert svc.store.notes("V") == [] and "V" not in load_vaults()
    assert svc.store.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


# --- final-review fixes -------------------------------------------------------------------

class RejectingEmbedder:
    """Rejects any batch containing a marker, the way Ollama rejects over-long input."""

    def __init__(self, inner, marker: str) -> None:
        self.inner, self.marker = inner, marker

    def embed_documents(self, texts):
        from vaultdb.embedder import EmbedderInputError
        if any(self.marker in t for t in texts):
            raise EmbedderInputError("Ollama returned 400: the input length exceeds the context length")
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def test_one_rejected_note_does_not_abort_the_vault(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    (fixture_vault / "Notes" / "poison.md").write_text("# Poison\n\nzzpoisonzz\n", encoding="utf-8")
    svc = VaultService(Store(tmp_path / "db.sqlite3"), RejectingEmbedder(fake_embedder, "zzpoisonzz"))
    info = svc.create_vault("V", str(fixture_vault))
    assert info["failed"] == [str(fixture_vault / "Notes" / "poison.md")]
    assert info["note_count"] == _md_count(fixture_vault) - 1
    assert svc.search_vault("V", "glass button")


def test_refresh_reports_rejected_notes_and_still_removes_deleted_ones(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    svc = VaultService(Store(tmp_path / "db.sqlite3"), RejectingEmbedder(fake_embedder, "zzpoisonzz"))
    svc.create_vault("V", str(fixture_vault))
    (fixture_vault / "Notes" / "poison.md").write_text("zzpoisonzz\n", encoding="utf-8")
    (fixture_vault / "Notes" / "gamma.md").unlink()
    result = svc.refresh_vault("V")
    assert result["removed"] == 1 and result["failed"] == [str(fixture_vault / "Notes" / "poison.md")]


def test_search_on_missing_source_folder_is_clear_error(svc, fixture_vault: Path, tmp_path: Path) -> None:
    moved = tmp_path / "moved2"
    shutil.copytree(fixture_vault, moved)
    svc.create_vault("V", str(moved))
    shutil.rmtree(moved)
    with pytest.raises(VaultError, match="source folder not found"):
        svc.search_vault("V", "glass")


def test_save_note_writes_bytes_unchanged(svc, fixture_vault: Path) -> None:
    svc.create_vault("V", str(fixture_vault))
    path = fixture_vault / "Notes" / "beta.md"
    svc.save_note("V", str(path), "# Beta\nline two\n")
    assert path.read_bytes() == b"# Beta\nline two\n"  # no \r\n translation on Windows
    svc.save_note("V", str(path), "# Beta\r\nkept crlf\r\n")
    assert path.read_bytes() == b"# Beta\r\nkept crlf\r\n"


def test_refresh_does_not_overwrite_vaults_added_by_another_process(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    app = VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder)
    app.create_vault("V", str(fixture_vault))
    mcp = VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder)  # loaded config before W existed
    other = tmp_path / "other"
    shutil.copytree(fixture_vault / "Notes", other)
    app.create_vault("W", str(other))
    mcp.refresh_vault("V")
    assert set(load_vaults()) == {"V", "W"}


def test_reload_vaults_picks_up_changes_from_another_process(tmp_path, data_dir, fake_embedder, fixture_vault) -> None:
    a = VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder)
    b = VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder)
    a.create_vault("V", str(fixture_vault))
    b.reload_vaults()
    assert "V" in b.vaults
