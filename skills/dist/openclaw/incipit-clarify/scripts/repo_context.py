#!/usr/bin/env python3
"""Print a compact Markdown summary of a codebase, for grounding a spec in the
repo that actually exists instead of a greenfield guess.

Standard library only, so it runs anywhere python3 does.

    python3 repo_context.py [path] [--max-chars N]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Manifest / config files that identify the stack, mapped to what they imply.
STACK_MARKERS = {
    "package.json": "Node.js / JavaScript",
    "pyproject.toml": "Python (PEP 621 project)",
    "requirements.txt": "Python (pip requirements)",
    "Pipfile": "Python (pipenv)",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java / Kotlin (Gradle)",
    "build.gradle.kts": "Kotlin (Gradle)",
    "composer.json": "PHP",
    "Package.swift": "Swift",
    "pubspec.yaml": "Dart / Flutter",
    "mix.exs": "Elixir",
    "deno.json": "Deno",
    "Dockerfile": "Docker image build",
    "docker-compose.yml": "Docker Compose",
    "compose.yaml": "Docker Compose",
    "Makefile": "Make-driven builds",
}

# Directories never worth walking when git is unavailable.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".nuxt", "target", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", "vendor", ".tox", ".gradle", "coverage",
}

README_NAMES = ("README.md", "README.rst", "README.txt", "README")


def list_files(root: Path) -> list[str]:
    """Repo-relative file paths, preferring git so ignored files stay out."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return sorted(line for line in out.stdout.splitlines() if line)
    except (OSError, subprocess.SubprocessError):
        pass

    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            found.append(rel)
        if len(found) > 20_000:  # pathological tree; the sample below is enough
            break
    return sorted(found)


def detect_stack(root: Path, files: set[str]) -> list[str]:
    hits = [label for marker, label in STACK_MARKERS.items() if marker in files]
    if any(f.endswith((".ts", ".tsx")) for f in files):
        hits.append("TypeScript")
    if (root / ".github" / "workflows").is_dir():
        hits.append("GitHub Actions CI")
    # Deduplicate while preserving discovery order.
    return list(dict.fromkeys(hits))


def detect_commands(root: Path, files: set[str]) -> list[str]:
    """Test / build commands the repo itself declares."""
    commands: list[str] = []
    if "package.json" in files:
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            for name, script in (data.get("scripts") or {}).items():
                if name in ("test", "build", "lint", "dev", "start"):
                    commands.append(f"npm run {name}  # {script}")
        except (OSError, ValueError):
            pass
    if {"pytest.ini", "tox.ini", "pyproject.toml"} & files:
        commands.append("pytest")
    if "Cargo.toml" in files:
        commands.append("cargo test")
    if "go.mod" in files:
        commands.append("go test ./...")
    if "Makefile" in files:
        commands.append("make  # see Makefile targets")
    return commands


def read_readme(root: Path, files: set[str], limit: int = 1500) -> str:
    for name in README_NAMES:
        if name in files:
            try:
                return (root / name).read_text(encoding="utf-8", errors="replace")[:limit]
            except OSError:
                return ""
    return ""


def build_summary(root: Path, max_chars: int) -> str:
    files = list_files(root)
    fileset = set(files)
    top = sorted({f.split("/")[0] for f in files})

    parts = [
        f"# Repo context: {root.resolve().name}",
        "",
        f"**Files tracked:** {len(files)}",
        f"**Detected stack:** {', '.join(detect_stack(root, fileset)) or 'unknown'}",
        f"**Top-level entries:** {', '.join(top[:40]) or '(none)'}",
    ]

    commands = detect_commands(root, fileset)
    if commands:
        parts += ["", "## Declared commands", ""]
        parts += [f"- `{c}`" for c in commands]

    parts += ["", "## File sample", "", "```"]
    parts += files[:150]
    parts += ["```"]

    readme = read_readme(root, fileset)
    if readme:
        parts += ["", "## README excerpt", "", readme.strip()]

    return "\n".join(parts)[:max_chars]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=".", help="repo root (default: cwd)")
    ap.add_argument("--max-chars", type=int, default=6000,
                    help="cap the summary so it stays prompt-sized (default: 6000)")
    args = ap.parse_args()

    root = Path(args.path).expanduser()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    print(build_summary(root, args.max_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
