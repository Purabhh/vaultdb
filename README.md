# VaultDB

A native desktop knowledge base that replaces Obsidian's markdown files with a vector database. Import your Obsidian vault, search semantically, and explore connections through an interactive graph — powered entirely by local AI.

## How It Works

```
Obsidian Vault (.md files)
    ↓  parse markdown, extract [[wikilinks]], tags, frontmatter
    ↓  chunk text into ~512 token segments
Ollama (nomic-embed-text)
    ↓  convert chunks into 768-dim vectors
Qdrant (vector DB)
    ↓  store vectors + metadata, enable similarity search
Tauri App (React + Rust)
    → interactive force-directed graph (link + semantic edges)
    → natural language search across all notes
```

## Features

- **Vault system** — create multiple vaults from different Obsidian directories, each stored as an isolated Qdrant collection
- **Obsidian import** — parses markdown, YAML frontmatter, `[[wikilinks]]`, `#tags`, and handles aliases
- **Semantic search** — find notes by meaning, not just keywords
- **Dual-layer graph** — explicit link edges (from wikilinks) + semantic edges (from vector similarity) — something Obsidian can't do
- **Fully local** — no cloud, no accounts, your data stays on your machine
- **Native app** — built with Tauri (Rust + WebKit), ~10MB vs Electron's 150MB+

## Vision

Obsidian is great but its graph is surface-level — it only knows what you explicitly link. VaultDB adds a semantic layer: notes that discuss similar topics get connected automatically, even if you never linked them. The goal is a knowledge base that understands your notes the way you do.

Future directions:
- **Auto-sync** — watch vault folders for changes and re-ingest in real time
- **Note editor** — edit markdown directly in-app with live vector updates
- **Semantic clusters** — auto-group related notes into topics
- **Cross-vault search** — search across all vaults at once
- **ONNX fallback** — bundled embedding model so Ollama isn't required

## Prerequisites

- **macOS** (arm64 or x86_64)
- **Rust** — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Node.js** — v18+
- **Ollama** — install from [ollama.com](https://ollama.com), then pull the embedding model:
  ```bash
  ollama pull nomic-embed-text
  ```
- **Qdrant** — download the binary from [GitHub releases](https://github.com/qdrant/qdrant/releases) for your platform, or run via Docker:
  ```bash
  # Option A: native binary
  ./qdrant

  # Option B: Docker
  docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
  ```

## Getting Started

1. **Start Qdrant:**
   ```bash
   qdrant  # must be running on localhost:6333/6334
   ```

2. **Start Ollama** (if not already running):
   ```bash
   ollama serve
   ```

3. **Clone and run:**
   ```bash
   git clone https://github.com/Purabhh/vaultdb.git
   cd vaultdb
   npm install
   npm run tauri dev
   ```

4. **Create a vault** — click `+` in the sidebar, name your vault, and browse to your Obsidian directory. Ingestion runs automatically.

## Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 (Rust + WebKit) |
| Frontend | React + TypeScript + Vite |
| Graph rendering | react-force-graph-2d (d3-force) |
| Vector database | Qdrant (local, gRPC) |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| Markdown parsing | pulldown-cmark + gray_matter |

## License

MIT
