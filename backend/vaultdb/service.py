"""Vault and note operations shared by the desktop app and the MCP server.

Method names and return shapes mirror the old Tauri commands (src/types.ts).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np

from .chunker import build_index_docs
from .components import parse_component
from .config import IndexOptions, VaultInfo, load_vaults, save_vaults
from .embedder import EmbedderError
from .markdown import parse_markdown_file, read_note_text
from .search import search
from .store import Store

SIMILAR_PER_CHUNK = 5


class VaultError(Exception):
    """A user-facing error with a readable message."""


def _clean_name(name: str) -> str:
    return name.strip().replace("/", "").replace("\\", "")


def _real(p: Path | str) -> Path:
    return Path(os.path.realpath(p))


def markdown_files(root: Path) -> list[Path]:
    """Every .md file under root, skipping hidden folders and files (like .obsidian, .trash)."""
    out = []
    for p in root.rglob("*.md"):
        rel = p.relative_to(root)
        if not any(part.startswith(".") for part in rel.parts) and p.is_file():
            out.append(p)
    return sorted(out)


class VaultService:
    def __init__(self, store: Store, embedder, opts: IndexOptions = IndexOptions()) -> None:
        self.store = store
        self.embedder = embedder
        self.opts = opts
        self.vaults: dict[str, VaultInfo] = load_vaults()

    # --- helpers -----------------------------------------------------------------------
    def _vault(self, name: str) -> VaultInfo:
        if name not in self.vaults:
            raise VaultError(f"Vault '{name}' not found")
        return self.vaults[name]

    def _root(self, name: str) -> Path:
        root = Path(self._vault(name).source_path)
        if not root.is_dir():
            raise VaultError(f"Vault '{name}': source folder not found: {root}")
        return root

    def validate_path(self, vault_name: str, note_path: str) -> Path:
        root = _real(self._root(vault_name))
        target = _real(note_path)
        if target != root and root not in target.parents:
            raise VaultError("Path traversal denied: path is outside the vault")
        return Path(note_path)

    def _save(self) -> None:
        save_vaults(self.vaults)

    def _index_file(self, vault: str, path: Path) -> None:
        note = parse_markdown_file(path)
        comp = parse_component(note, Path(self.vaults[vault].source_path))
        docs = build_index_docs(note, comp, self.opts)
        vectors = self.embedder.embed_documents([d.text for d in docs])
        self.store.upsert_note(vault, note, comp, path.stat().st_mtime, docs, vectors)

    # --- vaults ------------------------------------------------------------------------
    def list_vaults(self) -> list[dict]:
        return [v.to_dict() for v in self.vaults.values()]

    def create_vault(self, name: str, source_path: str) -> dict:
        if name in self.vaults:
            raise VaultError(f"Vault '{name}' already exists")
        root = Path(source_path)
        if not root.is_dir():
            raise VaultError(f"Folder not found: {source_path}")
        self.vaults[name] = VaultInfo(name, source_path, 0)
        count = 0
        try:
            for path in markdown_files(root):
                try:
                    self._index_file(name, path)
                except OSError:
                    continue
                count += 1
        except EmbedderError as e:
            self.store.delete_vault(name)
            del self.vaults[name]
            raise VaultError(str(e)) from e
        self.vaults[name].note_count = count
        self._save()
        return self.vaults[name].to_dict()

    def create_new_vault(self, name: str, parent_dir: str) -> dict:
        clean = _clean_name(name)
        if not clean:
            raise VaultError("Vault name cannot be empty")
        if clean in self.vaults:
            raise VaultError(f"Vault '{clean}' already exists")
        vault_dir = Path(parent_dir) / clean
        if vault_dir.exists():
            raise VaultError(f"Directory already exists: {vault_dir}")
        vault_dir.mkdir(parents=True)
        self.vaults[clean] = VaultInfo(clean, str(vault_dir), 0)
        self._save()
        return self.vaults[clean].to_dict()

    def delete_vault(self, name: str) -> None:
        self._vault(name)
        self.store.delete_vault(name)
        del self.vaults[name]
        self._save()

    def refresh_vault(self, vault_name: str) -> dict:
        root = self._root(vault_name)
        on_disk = {str(p): p for p in markdown_files(root)}
        indexed = self.store.note_mtimes(vault_name)
        added = updated = removed = 0
        try:
            for key, path in on_disk.items():
                if key not in indexed:
                    self._index_file(vault_name, path)
                    added += 1
                elif path.stat().st_mtime != indexed[key]:
                    self._index_file(vault_name, path)
                    updated += 1
        except EmbedderError as e:
            raise VaultError(str(e)) from e
        for key in indexed.keys() - on_disk.keys():
            self.store.delete_note(vault_name, key)
            removed += 1
        self.vaults[vault_name].note_count = len(on_disk)
        self._save()
        return {"added": added, "updated": updated, "removed": removed}

    # --- search & browse ---------------------------------------------------------------
    def search_vault(self, vault_name: str, query: str, limit: int = 10) -> list[dict]:
        self._vault(vault_name)
        try:
            hits = search(self.store, self.embedder, query, vault=vault_name, limit=limit, opts=self.opts)
        except ValueError as e:
            raise VaultError(str(e)) from e
        except EmbedderError as e:
            raise VaultError(str(e)) from e
        return [{"title": h.title, "path": h.path, "chunk": h.chunk, "score": h.score} for h in hits]

    def get_file_tree(self, vault_name: str) -> dict:
        return _file_tree(self._root(vault_name))

    def get_note_detail(self, vault_name: str, note_path: str) -> dict:
        path = self.validate_path(vault_name, note_path)
        if not path.is_file():
            raise VaultError(f"Note not found: {note_path}")
        note = parse_markdown_file(path)
        chunks = self.store.chunks_for_note(vault_name, note_path)
        if not chunks:
            try:
                self._index_file(vault_name, path)
            except EmbedderError as e:
                raise VaultError(str(e)) from e
            chunks = self.store.chunks_for_note(vault_name, note_path)
        matrix, ids = self.store.vector_matrix(vault_name, {"card", "code", "prose"})
        details = []
        for i, chunk in enumerate(chunks):
            similar: list[dict] = []
            if ids:
                sims = matrix @ chunk["embedding"]
                order = [ids[j] for j in np.argsort(-sims)[:SIMILAR_PER_CHUNK * 4]]
                meta = self.store.chunk_meta(order)
                score = dict(zip(ids, sims.tolist()))
                for cid in order:
                    m = meta.get(cid)
                    if m is None or m["path"] == note_path:
                        continue
                    similar.append({"title": m["title"], "chunk": m["text"], "score": float(score[cid])})
                    if len(similar) == SIMILAR_PER_CHUNK:
                        break
            details.append({"index": i, "text": chunk["text"], "similar_notes": similar})
        return {
            "title": note.title, "path": note_path, "raw_content": read_note_text(path),
            "tags": note.tags, "links": note.links, "chunks": details,
        }

    # --- notes & folders ---------------------------------------------------------------
    def save_note(self, vault_name: str, note_path: str, content: str) -> None:
        path = self.validate_path(vault_name, note_path)
        path.write_text(content, encoding="utf-8")
        try:
            self._index_file(vault_name, path)
        except EmbedderError as e:
            raise VaultError(f"Saved, but could not re-index: {e}") from e

    def reembed_note(self, vault_name: str, note_path: str) -> dict:
        path = self.validate_path(vault_name, note_path)
        try:
            self._index_file(vault_name, path)
        except EmbedderError as e:
            raise VaultError(str(e)) from e
        return self.get_note_detail(vault_name, note_path)

    def create_note(self, vault_name: str, parent_dir: str, file_name: str) -> str:
        parent = self.validate_path(vault_name, parent_dir)
        clean = _clean_name(file_name)
        if not clean or clean == ".md":
            raise VaultError("Note name cannot be empty")
        name = clean if clean.endswith(".md") else f"{clean}.md"
        full = parent / name
        if full.exists():
            raise VaultError(f"File already exists: {full}")
        full.write_text(f"# {name[:-3]}\n", encoding="utf-8")
        self.vaults[vault_name].note_count += 1
        self._save()
        return str(full)

    def delete_note(self, vault_name: str, note_path: str) -> None:
        path = self.validate_path(vault_name, note_path)
        try:
            path.unlink()
        except OSError as e:
            raise VaultError(f"Failed to delete file: {e}") from e
        self.store.delete_note(vault_name, note_path)
        info = self.vaults[vault_name]
        info.note_count = max(0, info.note_count - 1)
        self._save()

    def create_folder(self, vault_name: str, parent_dir: str, folder_name: str) -> str:
        parent = self.validate_path(vault_name, parent_dir)
        clean = _clean_name(folder_name)
        if not clean:
            raise VaultError("Folder name cannot be empty")
        full = parent / clean
        if full.exists():
            raise VaultError(f"Folder already exists: {full}")
        full.mkdir()
        return str(full)

    def delete_folder(self, vault_name: str, folder_path: str) -> None:
        target = self.validate_path(vault_name, folder_path)
        root = self._root(vault_name)
        if _real(target) == _real(root):
            raise VaultError("Cannot delete the vault root or paths outside the vault")
        shutil.rmtree(target)
        prefix = folder_path.rstrip("/\\")
        for key in list(self.store.note_mtimes(vault_name)):
            if key.startswith(prefix + "/") or key.startswith(prefix + "\\"):
                self.store.delete_note(vault_name, key)
        self.vaults[vault_name].note_count = len(markdown_files(root))
        self._save()

    def rename_item(self, vault_name: str, old_path: str, new_name: str) -> str:
        old = self.validate_path(vault_name, old_path)
        clean = _clean_name(new_name)
        if not clean:
            raise VaultError("Name cannot be empty")
        new = old.parent / clean
        if new.exists():
            raise VaultError(f"'{clean}' already exists")
        os.rename(old, new)
        self.store.rename_path(vault_name, old_path, str(new))
        if new.is_file() and new.suffix == ".md":
            try:
                self._index_file(vault_name, new)
            except EmbedderError:
                pass  # path is already updated; content refreshes on the next save or refresh
        return str(new)


def _file_tree(path: Path) -> dict:
    node = {"name": path.name or "root", "path": str(path), "is_dir": path.is_dir(), "children": []}
    if not path.is_dir():
        return node
    children = []
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            children.append(_file_tree(entry))
        elif entry.suffix == ".md":
            children.append({"name": entry.name, "path": str(entry), "is_dir": False, "children": []})
    children.sort(key=lambda c: (not c["is_dir"], c["name"].lower()))
    node["children"] = children
    return node
