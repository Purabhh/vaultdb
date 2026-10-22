"""Parse an Obsidian markdown note.

Frontmatter, [[wikilinks]] and #tags follow the original Rust parser exactly (see
tests/fixtures/rust_snapshots.json). Unlike the Rust version, code blocks are kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedNote:
    title: str
    path: str
    content: str
    links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    frontmatter: dict[str, str] = field(default_factory=dict)
    code_blocks: list[tuple[str, str]] = field(default_factory=list)
    prose: str = ""


def read_note_text(path: Path) -> str:
    """Read a note as UTF-8, replacing undecodable bytes and dropping a leading BOM."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    return text[1:] if text.startswith("﻿") else text


def parse_markdown_file(path: Path) -> ParsedNote:
    raw = read_note_text(path)
    frontmatter, body = extract_frontmatter(raw)
    code_blocks, prose_md = split_code_blocks(body)
    return ParsedNote(
        title=path.stem or "Untitled",
        path=str(path),
        content=body,
        links=extract_wikilinks(body),
        tags=extract_tags(body, frontmatter),
        frontmatter=frontmatter,
        code_blocks=code_blocks,
        prose=markdown_to_plain(prose_md),
    )


def extract_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    fm: dict[str, str] = {}
    if not raw.startswith("---"):
        return fm, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return fm, raw
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
    return fm, parts[2]


def extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "[" and i + 1 < n and text[i + 1] == "[":
            j = i + 2
            end = text.find("]", j)
            inner = text[j:] if end == -1 else text[j:end]
            target = inner.split("|", 1)[0].strip()
            if target:
                links.append(target)
            i = n if end == -1 else end + 1
        else:
            i += 1
    return links


def _trim_tag(word: str) -> str:
    keep = lambda c: c.isalnum() or c in "-_"  # noqa: E731
    start, end = 0, len(word)
    while start < end and not keep(word[start]):
        start += 1
    while end > start and not keep(word[end - 1]):
        end -= 1
    return word[start:end]


def extract_tags(text: str, fm: dict[str, str]) -> list[str]:
    tags: list[str] = []
    if "tags" in fm:
        for t in fm["tags"].strip("[]").split(","):
            t = t.strip().strip('"').strip("'")
            if t:
                tags.append(t)
    for word in text.split():
        if word.startswith("#") and len(word) > 1:
            tag = _trim_tag(word.lstrip("#"))
            if tag:
                tags.append(tag)
    return sorted(set(tags))


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def split_code_blocks(body: str) -> tuple[list[tuple[str, str]], str]:
    """Return ([(language, code), ...], body with the fenced blocks removed)."""
    blocks: list[tuple[str, str]] = []
    prose_lines: list[str] = []
    fence: str | None = None
    lang = ""
    code: list[str] = []
    for line in body.splitlines():
        if fence is None:
            m = _FENCE.match(line)
            if m:
                fence = m.group(1)
                info = m.group(2).strip()
                lang = info.split()[0].lower() if info else ""
                code = []
            else:
                prose_lines.append(line)
        else:
            stripped = line.strip()
            if stripped.startswith(fence[0] * len(fence)) and set(stripped) == {fence[0]}:
                blocks.append((lang, "\n".join(code)))
                fence = None
            else:
                code.append(line)
    if fence is not None:
        blocks.append((lang, "\n".join(code)))
    return blocks, "\n".join(prose_lines)


_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_WIKI = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
_HTML = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_QUOTE = re.compile(r"^\s*>\s?", re.M)
_EMPH = re.compile(r"(\*\*|__|\*|_|~~|`)")
_RULE = re.compile(r"^\s*([-*_]\s*){3,}$", re.M)


def markdown_to_plain(md: str) -> str:
    """Flatten markdown (no code blocks) to plain text, keeping line breaks."""
    text = _IMAGE.sub(r"\1", md)
    text = _WIKI.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    text = _LINK.sub(r"\1", text)
    text = _HTML.sub(" ", text)
    text = _RULE.sub("", text)
    text = _HEADING.sub("", text)
    text = _LIST.sub("", text)
    text = _QUOTE.sub("", text)
    text = _EMPH.sub("", text)
    text = text.replace("|", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
