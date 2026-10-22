"""vaultdb MCP server: lets agents (Claude Code) search the component library and fetch full code.

Add it to Claude Code with:  claude mcp add vaultdb -- <path to .venv>/bin/vaultdb-mcp
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .config import db_path, import_legacy_echidna
from .embedder import Embedder, EmbedderError
from .search import search
from .service import VaultError, VaultService
from .store import Store

INSTRUCTIONS = ("Before building or styling UI, search the component library and adapt what you find "
                "instead of inventing components.")
PART_CHARS = 40_000
WHY_CHARS = 300


def _split_parts(text: str, limit: int = PART_CHARS) -> list[str]:
    """Contiguous slices of text, cut at line boundaries, each at most `limit` chars when possible."""
    parts, cur = [], ""
    for line in text.splitlines(keepends=True):
        if cur and len(cur) + len(line) > limit:
            parts.append(cur)
            cur = ""
        cur += line
    parts.append(cur)
    return parts


def build_server(service: VaultService) -> MCPServer:
    server = MCPServer("vaultdb", instructions=INSTRUCTIONS)
    store, embedder, opts = service.store, service.embedder, service.opts

    def root(vault: str) -> Path:
        return Path(service.vaults[vault].source_path)

    def rel(vault: str, path: str) -> str:
        try:
            return Path(path).relative_to(root(vault)).as_posix()
        except (ValueError, KeyError):
            return path

    def run_search(query: str, vault: str | None, limit: int, components_only: bool):
        try:
            return search(store, embedder, query, vault=vault, limit=limit, opts=opts,
                          components_only=components_only)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except EmbedderError as e:
            raise ToolError(str(e)) from e

    def components() -> list[dict]:
        return [n for n in store.notes() if n["is_component"] and n["vault"] in service.vaults]

    @server.tool()
    def search_components(query: str, limit: int = 5, category: str | None = None) -> dict:
        """Search the UI component library by what a component looks like or does.

        Returns the best matches (name, category, tags, dependencies, why it matched, path).
        Then call get_component with the path to get the complete code.
        """
        fetch = limit * 6 if category else limit
        hits = run_search(query, None, fetch, components_only=True)
        if category:
            hits = [h for h in hits if h.category.lower() == category.lower()]
        return {"results": [
            {"name": h.title, "category": h.category, "tags": h.tags, "dependencies": h.dependencies,
             "score": round(h.score, 4), "why": h.chunk[:WHY_CHARS], "path": rel(h.vault, h.path),
             "vault": h.vault}
            for h in hits[:limit]
        ]}

    @server.tool()
    def get_component(name: str | None = None, path: str | None = None, part: int = 1) -> str:
        """Return a component note exactly as written: metadata, usage notes and the complete code.

        Identify it by `path` (as returned by search_components) or by `name`. Very large notes
        come in parts; follow the [continued: ...] marker at the end of each part.
        """
        comps = components()
        match = None
        if path:
            match = next((c for c in comps if rel(c["vault"], c["path"]) == path or c["path"] == path), None)
            if match is None:
                raise ToolError(f"No component at path '{path}'. Use search_components or list_components.")
        elif name:
            wanted = name.strip().lower()
            match = next((c for c in comps if c["title"].lower() == wanted
                          or Path(c["path"]).stem.lower() == wanted.replace(" ", "-")), None)
            if match is None:
                close = difflib.get_close_matches(name, [c["title"] for c in comps], n=3, cutoff=0.5)
                hint = f" Did you mean: {', '.join(close)}?" if close else ""
                raise ToolError(f"No component named '{name}'.{hint}")
        else:
            raise ToolError("Pass either `name` or `path`.")

        vault_root = root(match["vault"])
        if not vault_root.is_dir():
            raise ToolError(f"Vault '{match['vault']}': source folder not found: {vault_root}")
        file = Path(match["path"])
        if not file.is_file():
            raise ToolError(f"Component file is missing on disk: {file}")
        text = file.read_text(encoding="utf-8", errors="replace")
        parts = _split_parts(text)
        if not 1 <= part <= len(parts):
            raise ToolError(f"part must be between 1 and {len(parts)}")
        chunk = parts[part - 1]
        if part < len(parts):
            chunk += f"\n[continued: part {part} of {len(parts)} — call get_component again with part={part + 1}]"
        return chunk

    @server.tool()
    def list_components(category: str | None = None) -> dict:
        """List every component in the library (name, category, tags), optionally for one category."""
        rows = [c for c in components() if not category or c["category"].lower() == category.lower()]
        return {"components": [{"name": c["title"], "category": c["category"], "tags": c["tags"]}
                               for c in sorted(rows, key=lambda c: (c["category"], c["title"]))]}

    @server.tool()
    def search_notes(query: str, vault: str | None = None, limit: int = 10) -> dict:
        """Semantic + keyword search over all notes (not just components), optionally in one vault."""
        if vault is not None and vault not in service.vaults:
            known = ", ".join(sorted(service.vaults)) or "none"
            raise ToolError(f"Vault '{vault}' not found. Known vaults: {known}")
        hits = run_search(query, vault, limit, components_only=False)
        return {"results": [
            {"title": h.title, "path": rel(h.vault, h.path), "vault": h.vault,
             "snippet": h.chunk[:WHY_CHARS], "score": round(h.score, 4)}
            for h in hits
        ]}

    return server


def main() -> None:
    if import_legacy_echidna():
        print("vaultdb-mcp: imported vault list from the old echidna build", file=sys.stderr)
    service = VaultService(Store(db_path()), Embedder())
    for name in list(service.vaults):
        try:
            changes = service.refresh_vault(name)
            print(f"vaultdb-mcp: refreshed '{name}': {changes}", file=sys.stderr)
        except VaultError as e:
            print(f"vaultdb-mcp: could not refresh '{name}': {e}", file=sys.stderr)
    build_server(service).run()


if __name__ == "__main__":
    main()
