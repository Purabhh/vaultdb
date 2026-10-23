# VaultDB

A local knowledge base for your Obsidian vault, built to give coding agents real context. VaultDB indexes your notes, including the code inside them, into a single local search index and serves it two ways:

- **A desktop app** to browse, edit and search your vault.
- **An MCP server** so agents like Claude Code can search the vault and pull exact notes while they work.

Everything runs on your machine. No cloud, no accounts.

## Why

I keep a curated library of UI components (from [21st.dev](https://21st.dev)) as Obsidian notes, and I want coding agents to build interfaces from those components instead of inventing their own. Pasting the whole library into an agent's context doesn't work: it skims, then falls back on its own style. VaultDB lets the agent search for the two or three components that fit the task and get their complete code.

## How it works

```
Obsidian vault (.md files)
  │  parse frontmatter, [[wikilinks]], #tags, and code blocks
  │  component notes → a "card" (name, tags, dependencies, exports, props, imports, techniques)
  │                    + code chunks split at top-level declarations
  ▼
Ollama (nomic-embed-text, 768-dim, search_document / search_query prefixes)
  ▼
SQLite (one file): notes, chunks, FTS5 keyword index, float32 vectors
  ▼
hybrid search: vector similarity + BM25 keywords, fused with reciprocal rank fusion
  ├── desktop app (pywebview window + React UI)
  └── MCP server (stdio) → Claude Code
```

- **One core, two front doors.** The desktop app and the MCP server share one Python package and one SQLite file. SQLite runs in WAL mode, so the app can write while the MCP server reads, and there is no database server to install.
- **Code-aware indexing.** A component note becomes a card describing what the component is and uses, plus code chunks split at declarations. Every chunk is kept small enough for the embedding model's context window.
- **Hybrid search.** Vector similarity finds components by meaning ("frosted glass button"); keyword search catches exact names and identifiers. Results are fused and returned one per note.
- **Always current.** The app watches the vault folder and re-indexes notes as they change. The MCP server brings the index up to date when it starts, in the background, so it never delays the agent.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- [Ollama](https://ollama.com) with the embedding model:
  ```bash
  ollama pull nomic-embed-text
  ```

## Run the desktop app

```bash
npm install
npm run build
cd backend
uv run vaultdb
```

Use `uv run vaultdb --dev` with `npm run dev` running to work on the UI with hot reload.

Click **+** in the sidebar, name the vault and pick your Obsidian folder. VaultDB indexes it and keeps it up to date while the app is open.

## Use it from Claude Code (MCP)

```bash
claude mcp add --scope user vaultdb -- /path/to/vaultdb/backend/.venv/bin/vaultdb-mcp
```

The server reads the same vaults as the app; the app does not need to be open.

| Tool | What it does |
|---|---|
| `search_components(query, limit=5, category?)` | Finds UI components by what they look like or do; returns name, category, tags, dependencies and why each matched |
| `get_component(name? / path?, part=1)` | Returns the note exactly as written, including the complete code (very large notes come in parts) |
| `list_components(category?)` | Lists every component in the library |
| `search_notes(query, vault?, limit=10)` | Hybrid search across all notes, not just components |

The server also tells the agent: *before building or styling UI, search the component library and adapt what you find instead of inventing components.*

## Build a standalone app

```bash
npm run build
cd backend
uv run pyinstaller ../vaultdb.spec --noconfirm   # → backend/dist/VaultDB.app on macOS
```

## Results

Measured on a real component library (39 components plus an index note), with 70 natural-language queries written before any tuning: 35 for development, 35 held out. Each query describes a component without naming it, for example "frosted glass button with a distortion effect".

**Retrieval, held-out queries:**

| Configuration | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---|---|---|
| Vector search over note text only (code removed, no prefixes) | 0.886 | 1.000 | 1.000 | 0.933 |
| + nomic task prefixes | 0.829 | 0.971 | 1.000 | 0.893 |
| + component cards and code chunks | 0.771 | 0.914 | 0.971 | 0.846 |
| **+ hybrid keyword search (VaultDB)** | **0.914** | **1.000** | **1.000** | **0.957** |

Component notes already describe themselves well in their titles, tags and usage notes, so plain vector search over that text ranks well. Code-aware cards alone hurt vector ranking; adding keyword search recovers it and gives the best first result (32 of 35 queries correct at rank 1). Indexing code is also what lets VaultDB return a component's complete source, which text-only search cannot.

**Performance** (Mac mini, Apple Silicon): indexing 40 notes into 104 chunks takes 6.5 s (6.2 notes/s, embedding included). A search takes 19.6 ms at p50 and 24.3 ms at p95; about 15 ms of that is Ollama embedding the query and 4 ms is SQLite plus fusion.

Reproduce:

```bash
cd backend
uv run python -m vaultdb.eval.retrieval --vault-path /path/to/Components --split heldout
uv run python -m vaultdb.eval.bench --vault-path /path/to/Components
```

## Tests

```bash
cd backend
uv run pytest
```

Unit tests cover parsing (checked against reference snapshots), component detection, chunking, the SQLite store (including concurrent writers and readers), hybrid search, the graph, the vault service and the file watcher. Tests marked `ollama` use a real Ollama and are skipped when it is not running. The MCP tests start the real server over stdio.

## Platform support

- **macOS:** fully tested (app, MCP server, all tests including the Ollama ones).
- **Windows:** the packaged app (`VaultDB.exe`) builds and opens, the UI and the Python bridge work, and the test suite passes apart from the tests that need Ollama. Indexing a vault on Windows has not been tested yet.

On Windows, if `uv sync` fails while downloading Python, point it at an installed Python 3.11+: `$env:UV_PYTHON = "C:\path\to\python.exe"`.

## Stack

| Layer | Technology |
|---|---|
| Core | Python, SQLite (FTS5 + float32 vectors scanned with NumPy) |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| Agent interface | MCP server over stdio (official Python SDK) |
| Desktop shell | pywebview (WebKit on macOS, WebView2 on Windows) |
| Frontend | React + TypeScript + Vite, CodeMirror, react-force-graph |
| File watching | watchdog |

GitHub's language bar shows this repo as mostly TypeScript because the desktop frontend (React, CodeMirror, the graph view) is the largest share of the code. The indexing, search and MCP server, which are the core of VaultDB, are Python.

## License

MIT
