"""Protocol tests: spawn `python -m vaultdb.mcp_server` over stdio against a real fixture index."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from vaultdb.embedder import Embedder
from vaultdb.service import VaultService
from vaultdb.store import Store
from vaultdb.config import db_path


INSTRUCTIONS = ("Before building or styling UI, search the component library and adapt what you find "
                "instead of inventing components.")
HUGE_LINES = 5000


def _is_error(result) -> bool:
    return bool(getattr(result, "is_error", None) or getattr(result, "isError", None))


def _text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def _json(result):
    return json.loads(_text(result))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A data dir with the fixture vault (plus one huge component) indexed by the real embedder."""
    vault = tmp_path / "vault"
    shutil.copytree(Path(__file__).parent / "fixtures" / "vault", vault)
    code = "\n".join(f'  const row{i} = "px-4 py-2 rounded-md text-sm item-{i}"' for i in range(HUGE_LINES))
    (vault / "Buttons" / "huge-button.md").write_text(
        f"# Huge Button\n**Tags:** button, huge\n\n## Code\n\n```tsx\nexport function HugeButton() {{\n{code}\n}}\n```\n",
        encoding="utf-8")
    data = tmp_path / "data"
    monkeypatch.setenv("VAULTDB_DATA_DIR", str(data))
    svc = VaultService(Store(db_path()), Embedder())
    svc.create_vault("Components", str(vault))
    svc.store.close()
    return {"VAULTDB_DATA_DIR": str(data), "VAULT": str(vault), "PATH": os.environ.get("PATH", "")}


def _call(env: dict, fn):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "vaultdb.mcp_server"],
                                       env={k: v for k, v in env.items() if k != "VAULT"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                return await fn(session, init)
    return anyio.run(run)


@pytest.mark.ollama
def test_instructions_and_four_tools(env) -> None:
    async def fn(s, init):
        return init, await s.list_tools()
    init, tools = _call(env, fn)
    assert init.instructions == INSTRUCTIONS
    names = {t.name for t in tools.tools}
    assert names == {"search_components", "get_component", "list_components", "search_notes"}
    schema = next(t for t in tools.tools if t.name == "search_components")
    props = (getattr(schema, "input_schema", None) or getattr(schema, "inputSchema"))["properties"]
    assert {"query", "limit", "category"} <= set(props)


@pytest.mark.ollama
def test_search_components_finds_glass_button(env) -> None:
    async def fn(s, init):
        return await s.call_tool("search_components", {"query": "frosted glass button"})
    res = _json(_call(env, fn))["results"]
    assert "Buttons/liquid-glass-button.md" in [r["path"] for r in res[:3]]
    top = next(r for r in res if r["path"] == "Buttons/liquid-glass-button.md")
    assert top["name"] == "Liquid Glass Button" and top["category"] == "Buttons" and len(top["why"]) <= 300
    assert {"name", "category", "tags", "dependencies", "score", "why", "path", "vault"} <= set(top)


@pytest.mark.ollama
def test_search_components_category_filter(env) -> None:
    async def fn(s, init):
        return await s.call_tool("search_components", {"query": "animated", "category": "navigation"})
    res = _json(_call(env, fn))["results"]
    assert res and all(r["category"] == "Navigation" for r in res)


@pytest.mark.ollama
def test_get_component_returns_identical_code(env) -> None:
    async def fn(s, init):
        return await s.call_tool("get_component", {"path": "Buttons/liquid-glass-button.md"})
    text = _text(_call(env, fn))
    assert text == (Path(env["VAULT"]) / "Buttons/liquid-glass-button.md").read_text(encoding="utf-8")


@pytest.mark.ollama
def test_get_component_by_name(env) -> None:
    async def fn(s, init):
        return await s.call_tool("get_component", {"name": "liquid glass button"})
    assert "liquidbuttonVariants" in _text(_call(env, fn))


@pytest.mark.ollama
def test_unknown_component_suggests_close_names(env) -> None:
    async def fn(s, init):
        return await s.call_tool("get_component", {"name": "Liquid Glas Buton"})
    res = _call(env, fn)
    assert _is_error(res) and "Liquid Glass Button" in _text(res)


@pytest.mark.ollama
def test_large_note_is_split_with_marker(env) -> None:
    async def fn(s, init):
        parts = [await s.call_tool("get_component", {"path": "Buttons/huge-button.md", "part": 1})]
        n = int(_text(parts[0]).rsplit("part 1 of ", 1)[1].split()[0])
        for i in range(2, n + 1):
            parts.append(await s.call_tool("get_component", {"path": "Buttons/huge-button.md", "part": i}))
        return n, [_text(p) for p in parts]
    n, texts = _call(env, fn)
    assert n >= 2 and texts[0].rstrip().endswith("with part=2]")
    assert "[continued:" not in texts[-1]
    body = "".join(t.rsplit("\n[continued:", 1)[0] if i < n - 1 else t for i, t in enumerate(texts))
    assert body == (Path(env["VAULT"]) / "Buttons/huge-button.md").read_text(encoding="utf-8")


@pytest.mark.ollama
def test_list_components(env) -> None:
    async def fn(s, init):
        return await s.call_tool("list_components", {"category": "Cards"})
    names = {c["name"] for c in _json(_call(env, fn))["components"]}
    assert names == {"Animated Profile Card", "Morphing Card Stack"}


@pytest.mark.ollama
def test_search_notes_covers_plain_notes(env) -> None:
    async def fn(s, init):
        return await s.call_tool("search_notes", {"query": "layout ideas grid"})
    res = _json(_call(env, fn))["results"]
    assert any(r["path"].endswith("alpha.md") for r in res)
    assert {"title", "path", "vault", "snippet", "score"} <= set(res[0])


@pytest.mark.ollama
def test_unknown_vault_is_tool_error(env) -> None:
    async def fn(s, init):
        return await s.call_tool("search_notes", {"query": "x", "vault": "Nope"})
    res = _call(env, fn)
    assert _is_error(res) and "Nope" in _text(res)


@pytest.mark.ollama
def test_missing_source_folder_is_tool_error_not_crash(env) -> None:
    shutil.rmtree(env["VAULT"])

    async def fn(s, init):
        r = await s.call_tool("get_component", {"path": "Buttons/liquid-glass-button.md"})
        tools = await s.list_tools()  # server still up
        return r, tools
    res, tools = _call(env, fn)
    assert _is_error(res) and "source folder not found" in _text(res)
    assert len(tools.tools) == 4


@pytest.mark.ollama
def test_startup_imports_legacy_echidna_vaults(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(Path(__file__).parent / "fixtures" / "vault", vault)
    legacy = tmp_path / "echidna"
    legacy.mkdir()
    (legacy / "vaults.json").write_text(json.dumps(
        {"vaults": {"Components": {"name": "Components", "source_path": str(vault), "note_count": 0}}}))
    env = {"VAULTDB_DATA_DIR": str(tmp_path / "vaultdb"), "PATH": os.environ.get("PATH", "")}

    async def fn(s, init):
        return await s.call_tool("list_components", {"category": "Cards"})
    names = {c["name"] for c in _json(_call(env, fn))["components"]}
    assert names == {"Animated Profile Card", "Morphing Card Stack"}


@pytest.mark.ollama
def test_startup_refresh_sees_edit_made_before_launch(env) -> None:
    note = Path(env["VAULT"]) / "Notes/beta.md"
    note.write_text("# Beta\n\nThis note is now about narwhals.\n", encoding="utf-8")
    os.utime(note, (note.stat().st_atime, note.stat().st_mtime + 10))

    async def fn(s, init):
        return await s.call_tool("search_notes", {"query": "narwhals", "limit": 3})
    res = _json(_call(env, fn))["results"]
    assert res and res[0]["path"].endswith("beta.md") and "narwhals" in res[0]["snippet"]


@pytest.mark.ollama
def test_search_skips_vaults_whose_folder_is_gone(env) -> None:
    shutil.rmtree(env["VAULT"])

    async def fn(s, init):
        return (await s.call_tool("search_components", {"query": "glass button"}),
                await s.call_tool("search_notes", {"query": "glass", "vault": "Components"}))
    comps, notes = _call(env, fn)
    assert _is_error(comps) and "source folder not found" in _text(comps)
    assert _is_error(notes) and "source folder not found" in _text(notes)


@pytest.mark.ollama
def test_handshake_does_not_wait_for_indexing(env) -> None:
    # A changed note forces a re-index at startup; point Ollama at an address that never answers.
    note = Path(env["VAULT"]) / "Notes/beta.md"
    note.write_text("# Beta\n\nchanged\n", encoding="utf-8")
    os.utime(note, (note.stat().st_atime, note.stat().st_mtime + 10))
    slow = dict(env, VAULTDB_OLLAMA_URL="http://10.255.255.1:11434")
    import time as _time

    async def fn(s, init):
        return await s.list_tools()
    t = _time.monotonic()
    tools = _call(slow, fn)
    assert len(tools.tools) == 4 and _time.monotonic() - t < 20


def test_read_component_text_keeps_crlf(tmp_path: Path) -> None:
    from vaultdb.mcp_server import read_component_text
    p = tmp_path / "c.md"
    p.write_bytes(b"# C\r\n\r\n## Code\r\n")
    assert read_component_text(p) == "# C\r\n\r\n## Code\r\n"
