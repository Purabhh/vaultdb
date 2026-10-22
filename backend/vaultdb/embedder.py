"""Embeddings from a local Ollama server (nomic-embed-text, 768 dimensions)."""
from __future__ import annotations

import httpx
import numpy as np

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"
DIM = 768
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class EmbedderError(Exception):
    """Ollama could not produce embeddings; the message says what to do about it."""


class Embedder:
    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        use_prefixes: bool = True,
        batch_size: int = 32,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.use_prefixes = use_prefixes
        self.batch_size = batch_size
        self._client = httpx.Client(base_url=self.base_url, timeout=120, transport=transport)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        prefix = DOC_PREFIX if self.use_prefixes else ""
        rows = []
        for i in range(0, len(texts), self.batch_size):
            rows.append(self._embed([prefix + t for t in texts[i:i + self.batch_size]]))
        return np.vstack(rows)

    def embed_query(self, text: str) -> np.ndarray:
        prefix = QUERY_PREFIX if self.use_prefixes else ""
        return self._embed([prefix + text])[0]

    def _embed(self, inputs: list[str]) -> np.ndarray:
        try:
            resp = self._client.post("/api/embed", json={"model": self.model, "input": inputs})
        except httpx.ConnectError as e:
            raise EmbedderError(
                f"Ollama is not running at {self.base_url}. Start it (ollama serve) and try again."
            ) from e
        except httpx.HTTPError as e:
            raise EmbedderError(f"Request to Ollama failed: {e}") from e
        if resp.status_code == 404 and "not found" in resp.text:
            raise EmbedderError(
                f"The embedding model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if resp.status_code != 200:
            raise EmbedderError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
        vecs = np.asarray(resp.json().get("embeddings", []), dtype=np.float32)
        if vecs.ndim != 2 or vecs.shape != (len(inputs), DIM):
            raise EmbedderError(
                f"Expected {len(inputs)} embeddings of {DIM} dimensions from '{self.model}', got shape {vecs.shape}"
            )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
