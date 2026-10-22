"""Recognise UI component notes and pull out what makes each one findable.

A component note has a `## Code` heading followed by a fenced block, plus optional
`**Source:**`, `**Tags:**` and `**Dependencies:**` lines (the 21st.dev library format).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .markdown import ParsedNote, split_code_blocks


@dataclass
class ComponentInfo:
    name: str
    category: str
    source: str
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    code: str = ""
    language: str = ""
    exports: list[str] = field(default_factory=list)
    props: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)


_CODE_HEADING = re.compile(r"^##\s+Code\s*$", re.M)
_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.M)


def _meta(content: str, key: str) -> str:
    m = re.search(rf"^\*\*{key}:\*\*\s*(.*?)\s*$", content, re.M)
    return m.group(1) if m else ""


def split_list(value: str) -> list[str]:
    """Split on commas that are not inside parentheses."""
    items, depth, cur = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur).strip())
    return [i for i in items if i]


def parse_component(note: ParsedNote, vault_root: Path) -> ComponentInfo | None:
    heading = _CODE_HEADING.search(note.content)
    if not heading:
        return None
    blocks, _ = split_code_blocks(note.content[heading.end():])
    if not blocks:
        return None
    language, code = blocks[0]
    title = _TITLE.search(note.content)
    try:
        rel = Path(note.path).resolve().relative_to(Path(vault_root).resolve())
        category = rel.parts[0] if len(rel.parts) > 1 else ""
    except ValueError:
        category = ""
    sig = code_signature(code)
    return ComponentInfo(
        name=title.group(1) if title else note.title,
        category=category,
        source=_meta(note.content, "Source"),
        tags=split_list(_meta(note.content, "Tags")),
        dependencies=split_list(_meta(note.content, "Dependencies")),
        code=code,
        language=language,
        **sig,
    )


_EXPORT_DECL = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)", re.M)
_EXPORT_LIST = re.compile(r"^export\s*\{([^}]*)\}", re.M)
_PASCAL_FN = re.compile(r"^(?:async\s+)?function\s+([A-Z][\w$]*)\s*\(", re.M)
_PASCAL_CONST = re.compile(r"^const\s+([A-Z][\w$]*)\s*(?::[^=]+)?=\s*(?:React\.)?(?:forwardRef|memo|\(|async\s*\()", re.M)
_TYPE_DECL = re.compile(r"^(?:export\s+)?(?:interface|type)\s+([A-Z][\w$]*)", re.M)
_VARIANT_PROPS = re.compile(r"VariantProps<\s*typeof\s+([\w$]+)\s*>")
_IMPORT = re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""", re.M)

_TECHNIQUES: list[tuple[str, re.Pattern[str]]] = [
    ("animation", re.compile(r"framer-motion|motion/react|\bmotion\.|\bgsap\b")),
    ("keyframes", re.compile(r"@keyframes|\banimate-[\w-]+")),
    ("svg-filter", re.compile(r"feTurbulence|feDisplacementMap|<filter\b")),
    ("backdrop-filter", re.compile(r"backdrop-filter|backdropFilter|backdrop-blur")),
    ("3d", re.compile(r"""['"]three['"]|@react-three|preserve-3d|perspective|rotateX|rotateY""")),
    ("stateful", re.compile(r"\buseState\b")),
    ("scroll-trigger", re.compile(r"IntersectionObserver|useInView|ScrollTrigger|useScroll\b")),
]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def code_signature(code: str) -> dict[str, list[str]]:
    exports = _EXPORT_DECL.findall(code)
    for group in _EXPORT_LIST.findall(code):
        for part in group.split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                exports.append(name)
    jsx_used = set(re.findall(r"<([A-Z][\w$]*)", code))
    exports += [n for n in _PASCAL_FN.findall(code) + _PASCAL_CONST.findall(code) if n in jsx_used or not exports]
    props = _TYPE_DECL.findall(code) + _VARIANT_PROPS.findall(code)
    return {
        "exports": _dedupe(exports),
        "props": _dedupe(props),
        "imports": _dedupe(_IMPORT.findall(code)),
        "techniques": [name for name, pat in _TECHNIQUES if pat.search(code)],
    }
