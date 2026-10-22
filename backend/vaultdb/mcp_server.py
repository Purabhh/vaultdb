"""vaultdb MCP server: lets agents (Claude Code) search the component library and fetch full code.

Add it to Claude Code with:  claude mcp add vaultdb -- <path to .venv>/bin/vaultdb-mcp
"""
from __future__ import annotations

import difflib
import sys
import threading
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
REFRESH_WAIT_S = 10  # how long a tool waits for the startup refresh before using the index as-is
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


def read_component_text(path: Path) -> str:
    """The note exactly as stored (no newline translation), with undecodable bytes replaced."""
    return path.read_bytes().decode("utf-8", errors="replace")


def build_server(service: VaultService, ready: threading.Event | None = None) -> MCPServer:
    """`ready` is set once the startup refresh finishes; tools wait for it briefly so the first
    search sees fresh notes, while the protocol handshake never waits."""
    server = MCPServer("vaultdb", instructions=INSTRUCTIONS)

    def await_refresh() -> None:
        if ready is not None:
            ready.wait(REFRESH_WAIT_S)
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

    def searchable_vaults(only: str | None = None) -> list[str]:
        """Known vaults to search (re-read from disk, so vaults the app added later count), minus any
        whose folder is gone. If every requested vault is gone, that is a clear tool error."""
        await_refresh()
        service.reload_vaults()
        if only is not None and only not in service.vaults:
            known = ", ".join(sorted(service.vaults)) or "none"
            raise ToolError(f"Vault '{only}' not found. Known vaults: {known}")
        names = [only] if only is not None else sorted(service.vaults)
        alive = [v for v in names if root(v).is_dir()]
        if names and not alive:
            gone = "; ".join(f"Vault '{v}': source folder not found: {root(v)}" for v in names)
            raise ToolError(gone)
        return alive

    @server.tool()
    def search_components(query: str, limit: int = 5, category: str | None = None) -> dict:
        """Search the UI component library by what a component looks like or does.

        Returns the best matches (name, category, tags, dependencies, why it matched, path).
        Then call get_component with the path to get the complete code.
        """
        alive = set(searchable_vaults())
        fetch = limit * 6 if category else limit * 2
        hits = [h for h in run_search(query, None, fetch, components_only=True) if h.vault in alive]
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
        await_refresh()
        service.reload_vaults()
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
        text = read_component_text(file)
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
        await_refresh()
        service.reload_vaults()
        rows = [c for c in components() if not category or c["category"].lower() == category.lower()]
        return {"components": [{"name": c["title"], "category": c["category"], "tags": c["tags"]}
                               for c in sorted(rows, key=lambda c: (c["category"], c["title"]))]}

    @server.tool()
    def search_notes(query: str, vault: str | None = None, limit: int = 10) -> dict:
        """Semantic + keyword search over all notes (not just components), optionally in one vault."""
        alive = searchable_vaults(vault)
        hits = [h for h in run_search(query, vault, limit * 2, components_only=False) if h.vault in alive][:limit]
        return {"results": [
            {"title": h.title, "path": rel(h.vault, h.path), "vault": h.vault,
             "snippet": h.chunk[:WHY_CHARS], "score": round(h.score, 4)}
            for h in hits
        ]}

    return server


def refresh_all(done: threading.Event) -> None:
    """Bring every vault's index up to date. Runs on its own thread and SQLite connection."""
    try:
        service = VaultService(Store(db_path()), Embedder())
        for name in list(service.vaults):
            try:
                changes = service.refresh_vault(name)
                print(f"vaultdb-mcp: refreshed '{name}': {changes}", file=sys.stderr)
            except VaultError as e:
                print(f"vaultdb-mcp: could not refresh '{name}': {e}", file=sys.stderr)
        service.store.close()
    finally:
        done.set()


def main() -> None:
    if import_legacy_echidna():
        print("vaultdb-mcp: imported vault list from the old echidna build", file=sys.stderr)
    # Answer the client's handshake right away; indexing a large vault (or a slow Ollama) must
    # not hold up MCP startup. Searches see notes as soon as they are written.
    ready = threading.Event()
    threading.Thread(target=refresh_all, args=(ready,), name="vaultdb-refresh", daemon=True).start()
    build_server(VaultService(Store(db_path()), Embedder()), ready).run()


if __name__ == "__main__":
    main()
