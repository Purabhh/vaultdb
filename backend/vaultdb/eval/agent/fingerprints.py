"""Distinctive tokens of a component's code, used to detect whether an agent reused it."""
from __future__ import annotations

import re

from ...components import code_signature
from ...markdown import split_code_blocks

_TOP_LEVEL = re.compile(r"^(?:export\s+)?(?:const|let|function)\s+([A-Za-z_]\w{5,})", re.M)
_ARBITRARY_CLASS = re.compile(r"[\w:/.-]*-\[[^\]\s\"'`]{4,}\]")
_CLASS_STRING = re.compile(r"""className=\{?\s*["'`]([^"'`{}$]{40,})["'`]""")
# Names an agent would plausibly write on its own; matching them proves nothing.
_STOP = {"default", "children", "className", "handleClick", "onClick", "variants", "options", "useEffect",
         "useState", "useRef", "container", "content", "wrapper", "Component", "Cursor", "Tab", "Tabs",
         "Switch", "App", "Card", "Button", "Item", "Menu", "Header", "Footer", "Input", "Hero", "Demo"}


def fingerprints(text: str) -> set[str]:
    """Distinctive names, long arbitrary-value Tailwind classes and long className strings."""
    blocks, _ = split_code_blocks(text)
    code = "\n".join(c for _, c in blocks) if blocks else text
    names = set(code_signature(code)["exports"]) | set(_TOP_LEVEL.findall(code))
    classes = {c for c in _ARBITRARY_CLASS.findall(code) if len(c) >= 12}
    class_strings = {" ".join(s.split()) for s in _CLASS_STRING.findall(code) if len(s.split()) >= 5}
    return {n for n in names if n not in _STOP} | classes | class_strings
