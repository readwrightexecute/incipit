#!/usr/bin/env python3
"""Generate the per-harness skill adapters in skills/dist from skills/src.

skills/src holds one canonical copy of each skill. Harnesses differ only in
frontmatter and on-disk layout (see harnesses.json), so every adapter is
generated rather than hand-maintained — hand-maintained copies drift.

    python3 skills/build.py            # write skills/dist
    python3 skills/build.py --check    # fail if skills/dist is stale

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DIST = HERE / "dist"
MANIFEST = HERE / "harnesses.json"

GENERATED_NOTE = (
    "<!-- Generated from skills/src/{skill} by skills/build.py. Do not edit; "
    "edit the source and re-run the build. -->"
)

# Frontmatter values that YAML would misread as something other than a string.
# Interior quotes are fine in a plain scalar; a leading one is not.
_NEEDS_QUOTE = re.compile(r"""(^[\s>|&*!%@`\[\{#'"-])|(:\s)|(\s#)|(^$)""")


# --------------------------------------------------------------------------- #
# Minimal YAML emitting / frontmatter parsing
# --------------------------------------------------------------------------- #

def yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _NEEDS_QUOTE.search(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def emit_yaml(data: dict, indent: int = 0) -> list[str]:
    """Emit the small subset of YAML skill frontmatter needs: strings, flow
    lists of scalars, and nested mappings."""
    pad = "  " * indent
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.extend(emit_yaml(value, indent + 1))
        elif isinstance(value, list):
            inner = ", ".join(yaml_scalar(v) for v in value)
            lines.append(f"{pad}{key}: [{inner}]")
        else:
            lines.append(f"{pad}{key}: {yaml_scalar(value)}")
    return lines


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter, body). Source frontmatter is flat `key: value`."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a YAML frontmatter block")
    end = text.index("\n---\n", 3)
    raw, body = text[4:end + 1], text[end + 5:]

    front: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"unsupported frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        front[key.strip()] = _unquote(value.strip())
    return front, body.lstrip("\n")


def _unquote(value: str) -> str:
    """Strip surrounding quotes only when they are balanced — a description
    ending in a quoted phrase must not lose its closing quote."""
    for q in ('"', "'"):
        if len(value) >= 2 and value.startswith(q) and value.endswith(q):
            inner = value[1:-1]
            return inner.replace("\\" + q, q).replace("\\\\", "\\") if q == '"' else inner
    return value


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_skill_md(skill: str, source: str, extra_frontmatter: dict) -> str:
    front, body = split_frontmatter(source)
    merged = {**front, **extra_frontmatter}
    lines = ["---", *emit_yaml(merged), "---", GENERATED_NOTE.format(skill=skill), ""]
    return "\n".join(lines) + "\n" + body


def shift_headings(body: str) -> str:
    """Demote every Markdown heading one level, ignoring fenced code blocks, so
    a skill body can nest under a parent section in AGENTS.md."""
    out: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append("#" + line if not in_fence and line.startswith("#") else line)
    return "\n".join(out)


def slugify(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text).strip("-")


def render_agents_md(skills: list[str], preamble: str) -> str:
    """One self-contained document: every skill body plus the reference files
    they would otherwise load on demand, with relative links rewritten to
    in-document anchors."""
    bodies: list[str] = []
    appendix: list[str] = []
    link_map: dict[str, tuple[str, str]] = {}

    for skill in skills:
        skill_dir = SRC / skill
        _, body = split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
        bodies.append(shift_headings(body).strip())

        ref_dir = skill_dir / "reference"
        for ref in sorted(ref_dir.glob("*.md")) if ref_dir.is_dir() else []:
            ref_text = ref.read_text(encoding="utf-8")
            heading = next((l for l in ref_text.splitlines() if l.startswith("# ")),
                           f"# {ref.stem}")
            title = heading.lstrip("#").strip()
            anchor = f"#{slugify(heading)}"
            # Both the path used from SKILL.md and the bare name used when one
            # reference file links to a sibling.
            link_map[f"reference/{ref.name}"] = (title, anchor)
            link_map[ref.name] = (title, anchor)
            appendix.append(shift_headings(ref_text).strip())

    parts = ["# Incipit", "", preamble, ""]
    parts += ["\n\n---\n\n".join(bodies)]
    if appendix:
        parts += ["", "---", "", "\n\n---\n\n".join(appendix)]

    document = "\n".join(parts).rstrip() + "\n"
    # Longest path first, so `reference/x.md` is rewritten before the bare `x.md`
    # that is a suffix of it.
    for path in sorted(link_map, key=len, reverse=True):
        title, anchor = link_map[path]
        # A link whose text is just the path would name a file this single
        # document doesn't have; retitle it. Then repoint any remaining links.
        document = document.replace(f"[{path}]({path})", f"[{title}]({anchor})")
        document = document.replace(f"]({path})", f"]({anchor})")
    return document


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

# Artifacts that appear next to the sources but are not part of a skill. Running
# the test suite leaves __pycache__ beside the bundled scripts, and shipping a
# .pyc would also break the text-only copy below.
_NOISE = {"__pycache__", ".pytest_cache", ".DS_Store"}
_NOISE_SUFFIXES = {".pyc", ".pyo"}


def is_noise(path: Path) -> bool:
    return (path.suffix in _NOISE_SUFFIXES
            or bool(_NOISE.intersection(path.parts)))


def build() -> dict[str, str]:
    """Return the full desired contents of skills/dist, keyed by relative path."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    skills: list[str] = manifest["skills"]
    tree: dict[str, str] = {}

    for skill in skills:
        if not (SRC / skill / "SKILL.md").is_file():
            raise SystemExit(f"error: missing source skill: src/{skill}/SKILL.md")

    for harness in manifest["harnesses"]:
        hid = harness["id"]

        if harness["format"] == "agents_md":
            out = f"{hid}/{harness.get('output', 'AGENTS.md')}"
            tree[out] = render_agents_md(skills, harness.get("preamble", ""))
            continue

        for skill in skills:
            skill_dir = SRC / skill
            base = f"{hid}/{harness['layout'].format(skill=skill)}"
            tree[f"{base}/SKILL.md"] = render_skill_md(
                skill,
                (skill_dir / "SKILL.md").read_text(encoding="utf-8"),
                harness.get("frontmatter", {}),
            )
            for extra in sorted(skill_dir.rglob("*")):
                if extra.is_dir() or extra.name == "SKILL.md" or is_noise(extra):
                    continue
                rel = extra.relative_to(skill_dir).as_posix()
                tree[f"{base}/{rel}"] = extra.read_text(encoding="utf-8")

            # Files owned by another skill that this one's body tells the agent
            # to run. Bundling them keeps every installed skill self-contained,
            # including when a user installs a subset.
            for shared in manifest.get("shared_files", {}).get(skill, []):
                source = SRC / shared
                if not source.is_file():
                    raise SystemExit(f"error: shared file missing: src/{shared}")
                rel = Path(shared).relative_to(Path(shared).parts[0]).as_posix()
                tree[f"{base}/{rel}"] = source.read_text(encoding="utf-8")

    return tree


def current() -> dict[str, str]:
    if not DIST.is_dir():
        return {}
    return {
        p.relative_to(DIST).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(DIST.rglob("*")) if p.is_file() and not is_noise(p)
    }


def write(tree: dict[str, str]) -> None:
    if DIST.is_dir():
        shutil.rmtree(DIST)
    for rel, content in tree.items():
        target = DIST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if target.suffix == ".py":
            target.chmod(0o755)


def diff(expected: dict[str, str], found: dict[str, str]) -> list[str]:
    problems = [f"stale (content differs): {k}" for k in sorted(expected)
                if k in found and found[k] != expected[k]]
    problems += [f"missing from dist: {k}" for k in sorted(set(expected) - set(found))]
    problems += [f"not generated by the manifest: {k}" for k in sorted(set(found) - set(expected))]
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify skills/dist matches skills/src without writing")
    args = ap.parse_args()

    tree = build()

    if args.check:
        problems = diff(tree, current())
        if problems:
            print("skills/dist is out of date. Run: python3 skills/build.py",
                  file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"skills/dist is up to date ({len(tree)} files).")
        return 0

    write(tree)
    print(f"wrote {len(tree)} files to skills/dist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
