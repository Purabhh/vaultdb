# VaultDB

A local knowledge base for your Obsidian vault, built to give coding agents real context. VaultDB indexes your notes, including the code inside them, into a single local search index, and serves it two ways:

- **A desktop app** to browse, edit and search your vault (React UI in a native window).
- **An MCP server** so agents like Claude Code can search the vault and pull exact notes while they work.

It was built for one job in particular: a curated library of UI components (from [21st.dev](https://21st.dev)) kept as Obsidian notes. When Claude builds a UI, it should find the right component and reuse its actual code and design decisions instead of inventing its own. Dumping the whole library into context doesn't work; retrieving the two or three components that fit the task does.

Everything runs on your machine. No cloud, no accounts.

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

The app and the MCP server share one Python core and one SQLite file. SQLite in WAL mode lets the app write while the MCP server reads, and there is no database server to install.

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

Click **+** in the sidebar, name the vault and pick your Obsidian folder. VaultDB indexes it, then keeps it up to date as files change.

## Use it from Claude Code (MCP)

```bash
claude mcp add --scope user vaultdb -- /path/to/vaultdb/backend/.venv/bin/vaultdb-mcp
```

The server reads the same vaults as the app (it also brings the index up to date when it starts, so the app does not need to be open).

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

Measured on the real component vault (39 components plus an index note), with 70 natural-language queries written before any tuning (35 for development, 35 held out). The queries describe a component without naming it, for example "frosted glass button with a distortion effect".

**Retrieval, held-out queries:**

| Configuration | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---|---|---|
| Baseline (original behavior: code stripped, no prefixes, vector only) | 0.886 | 1.000 | 1.000 | 0.933 |
| + nomic task prefixes | 0.829 | 0.971 | 1.000 | 0.893 |
| + component cards and code chunks | 0.771 | 0.914 | 0.971 | 0.846 |
| **+ hybrid keyword search (final)** | **0.914** | **1.000** | **1.000** | **0.957** |

The original search already ranked well, because each note's title, tags and usage notes describe it. The bigger change is what comes back: the original never indexed or returned code, while VaultDB returns the complete component. Code-aware cards on their own hurt vector ranking; adding keyword search recovers it and lifts the top result.

**Performance** (Mac mini, Apple Silicon): indexing 40 notes into 104 chunks takes 6.5 s (6.2 notes/s, embedding included). A search takes 19.6 ms at p50 and 24.3 ms at p95; about 15 ms of that is Ollama embedding the query, 4 ms is SQLite plus fusion.

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

Unit tests cover parsing (checked against snapshots of the original Rust parser), component detection, chunking, the SQLite store (including a concurrent writer and reader), hybrid search, the graph, the vault service and the file watcher. Tests marked `ollama` use a real Ollama and are skipped when it is not running. The MCP tests start the real server over stdio.

## Platform support

Tested on macOS. Windows support is in progress.

## Stack

| Layer | Technology |
|---|---|
| Core | Python, SQLite (FTS5 + float32 vectors scanned with NumPy) |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| Agent interface | MCP server over stdio (official Python SDK) |
| Desktop shell | pywebview (WebKit on macOS) |
| Frontend | React + TypeScript + Vite, CodeMirror, react-force-graph |
| File watching | watchdog |

## License

MIT
