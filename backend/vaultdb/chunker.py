"""Turn a parsed note into the documents that get embedded and keyword-indexed."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .components import ComponentInfo
from .config import IndexOptions
from .markdown import ParsedNote

DocKind = Literal["card", "code", "prose"]


@dataclass
class IndexDoc:
    kind: DocKind
    idx: int
    text: str


def chunk_prose(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    """Word windows of `size` with `overlap`, same as the original Rust chunk_text."""
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    chunks, start = [], 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += size - overlap
    return chunks


_DECL = re.compile(r"^(export|function|const|class|interface|type)\b")


def chunk_code(code: str, max_lines: int = 120) -> list[str]:
    """Split code at top-level declarations, merge small neighbours, hard-split long ones."""
    lines = code.splitlines()
    if not any(line.strip() for line in lines):
        return []
    pieces: list[list[str]] = [[]]
    for line in lines:
        if _DECL.match(line) and any(l.strip() for l in pieces[-1]) and not _is_preamble(pieces[-1]):
            pieces.append([])
        pieces[-1].append(line)

    sized: list[list[str]] = []
    for piece in pieces:
        for i in range(0, len(piece), max_lines):
            sized.append(piece[i:i + max_lines])

    merged: list[list[str]] = []
    for piece in sized:
        if merged and len(merged[-1]) + len(piece) <= max_lines:
            merged[-1].extend(piece)
        else:
            merged.append(list(piece))
    return ["\n".join(p).strip("\n") for p in merged if any(l.strip() for l in p)]


def _is_preamble(lines: list[str]) -> bool:
    """Imports, directives and blank lines stay attached to the first declaration."""
    return all(
        not l.strip() or l.startswith(("import ", '"use ', "'use ", "//")) for l in lines
    )


def _card_text(c: ComponentInfo, prose: str) -> str:
    j = ", ".join
    return (
        f"{c.name}\nCategory: {c.category}\nSource: {c.source}\nTags: {j(c.tags)}\n"
        f"Dependencies: {j(c.dependencies)}\nExports: {j(c.exports)}\nProps: {j(c.props)}\n"
        f"Imports: {j(c.imports)}\nTechniques: {j(c.techniques)}\n{prose}"
    ).strip()


def build_index_docs(note: ParsedNote, component: ComponentInfo | None, opts: IndexOptions) -> list[IndexDoc]:
    docs: list[IndexDoc] = []
    if component is not None and opts.component_cards and opts.keep_code:
        docs.append(IndexDoc("card", 0, _card_text(component, note.prose)))
    else:
        docs += [IndexDoc("prose", i, t) for i, t in enumerate(chunk_prose(note.prose))]
    if opts.keep_code:
        code_chunks = [c for _, code in note.code_blocks for c in chunk_code(code)]
        docs += [IndexDoc("code", i, t) for i, t in enumerate(code_chunks)]
    return docs
