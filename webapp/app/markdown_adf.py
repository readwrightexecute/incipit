"""Minimal Markdown → Atlassian Document Format (ADF) converter.

Produces the "pretty" body for a Jira REST v3 issue `description` from the
mega-prompt markdown (flow.assemble_final). Supports the subset the wizard
emits: headings, paragraphs, bold/italic, inline + fenced code, bullet/ordered
lists, and links. Anything it doesn't recognize degrades to plain paragraph
text — never raises, so an export can't be blocked by an exotic snippet.

ADF reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
"""

import re

# One pass scans for the next inline span. Code is matched first so `**`/`_`
# inside a code span aren't treated as emphasis. Marks are flat (no nesting),
# which is all the assembled brief needs.
_INLINE_RE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*[^*]+?\*\*|__[^_]+?__)"
    r"|(?P<italic>\*[^*]+?\*|_[^_]+?_)"
    r"|(?P<link>\[[^\]]+\]\([^)\s]+\))"
)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^```(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_BLOCK_START_RE = re.compile(r"^(#{1,6}\s|```|\s*[-*+]\s+|\s*\d+\.\s+)")


def _push_text(nodes: list, text: str) -> None:
    if text:
        nodes.append({"type": "text", "text": text})


def _inline(text: str) -> list:
    """Parse inline markdown into a list of ADF text nodes (with marks)."""
    nodes: list = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            _push_text(nodes, text[pos:m.start()])
        if m.group("code"):
            _push_text_mark(nodes, m.group("code")[1:-1], {"type": "code"})
        elif m.group("bold"):
            _push_text_mark(nodes, m.group("bold")[2:-2], {"type": "strong"})
        elif m.group("italic"):
            _push_text_mark(nodes, m.group("italic")[1:-1], {"type": "em"})
        elif m.group("link"):
            lm = _LINK_RE.match(m.group("link"))
            label, href = lm.group(1), lm.group(2)
            _push_text_mark(nodes, label, {"type": "link", "attrs": {"href": href}})
        pos = m.end()
    if pos < len(text):
        _push_text(nodes, text[pos:])
    return nodes


def _push_text_mark(nodes: list, text: str, mark: dict) -> None:
    if text:
        nodes.append({"type": "text", "text": text, "marks": [mark]})


def _paragraph(text: str) -> dict | None:
    content = _inline(text)
    return {"type": "paragraph", "content": content} if content else None


def _collect_list(lines: list, i: int, rex: re.Pattern) -> tuple[list, int]:
    items: list = []
    n = len(lines)
    while i < n:
        m = rex.match(lines[i])
        if not m:
            break
        para = _paragraph(m.group(1).strip()) or {"type": "paragraph", "content": []}
        items.append({"type": "listItem", "content": [para]})
        i += 1
    return items, i


def to_adf(md: str) -> dict:
    """Convert markdown to an ADF document node (always a valid `doc`)."""
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    content: list = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            lang = fence.group(1).strip()
            i += 1
            code_lines: list = []
            while i < n and not line_is_fence(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # consume the closing fence (or run off the end)
            node = {"type": "codeBlock"}
            if lang:
                node["attrs"] = {"language": lang}
            code = "\n".join(code_lines)
            if code:
                node["content"] = [{"type": "text", "text": code}]
            content.append(node)
            continue
        if not line.strip():
            i += 1
            continue
        h = _HEADING_RE.match(line)
        if h:
            inner = _inline(h.group(2).strip()) or [{"type": "text", "text": h.group(2).strip()}]
            content.append({"type": "heading", "attrs": {"level": len(h.group(1))},
                            "content": inner})
            i += 1
            continue
        if _BULLET_RE.match(line):
            items, i = _collect_list(lines, i, _BULLET_RE)
            content.append({"type": "bulletList", "content": items})
            continue
        if _ORDERED_RE.match(line):
            items, i = _collect_list(lines, i, _ORDERED_RE)
            content.append({"type": "orderedList", "content": items})
            continue
        # paragraph: gather contiguous lines until a blank / block start
        para_lines = [line]
        i += 1
        while i < n and lines[i].strip() and not _BLOCK_START_RE.match(lines[i]):
            para_lines.append(lines[i])
            i += 1
        para = _paragraph(" ".join(s.strip() for s in para_lines))
        if para:
            content.append(para)
    if not content:
        content = [{"type": "paragraph", "content": []}]
    return {"version": 1, "type": "doc", "content": content}


def line_is_fence(line: str) -> bool:
    return line.lstrip().startswith("```")
