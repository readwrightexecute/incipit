#!/usr/bin/env python3
"""Verify an Implementation Brief, and optionally its task list, mechanically.

An agent rereading its own output is a poor judge of whether it followed the rules,
and self-assessed checklists degrade exactly when the output is long. Everything
here is structural: section presence and order, requirement syntax, ID numbering,
acceptance-criteria coverage, citation format, and task dependency ordering. Nothing
about content quality, which a script cannot judge.

Standard library only, so it runs anywhere python3 does.

    python3 brief_check.py docs/specs/foo/brief.md
    python3 brief_check.py docs/specs/foo/brief.md --tasks docs/specs/foo/tasks.md
    python3 brief_check.py docs/specs/foo/brief.md --research docs/specs/foo/research.md

Citations are checked for shape by default. Add --verify-sources to also fetch each
cited URL: format is verifiable offline, existence is not, so the network call is
opt-in.

Exit status is 0 when the brief passes and 1 when it does not.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SCHEMAS = {
    "software": [
        "Goals & Background",
        "Functional Requirements",
        "Non-Functional Requirements",
        "Tech Constraints & Stack",
        "Acceptance Criteria",
        "Out of Scope",
    ],
    "generic": [
        "Goals & Background",
        "Requirements",
        "Quality Bar",
        "Resources & Constraints",
        "Acceptance Criteria",
        "Out of Scope",
    ],
}

HEADER_FIELDS = ["Project idea (verbatim from the author)", "Project type", "Stakes",
                 "Form factor"]

RESEARCH_SECTIONS = ["Prior art", "Approach", "Pitfalls", "External constraints",
                     "Open questions"]
VERDICTS = ("build", "adopt", "extend")
# Distinct sources below this, and the research rested on too narrow a base to be
# worth citing as evidence.
MIN_DISTINCT_SOURCES = 2

SOURCE_TIMEOUT = 8.0
# A citation is meant to be something a reader can open. A loopback or private
# address is not, and fetching one would have this script probe its own network.
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", ""}

REQUIREMENT = re.compile(r"^\s*[-*]?\s*(N?FR\d+)\s*[:.]\s*(.+)$")
CRITERION = re.compile(r"^\s*[-*]?\s*(AC\d+)\s*[:.]\s*(.+)$")
COVERS = re.compile(r"^\[([^\]]*)\]")
ID_REF = re.compile(r"\bN?FR\d+\b")
# The EARS unwanted-behaviour pattern. Its presence is how "the brief covers an
# error path" becomes checkable — sniffing prose for words like "invalid" would
# guess, and guessing is what this script exists to avoid.
UNWANTED = re.compile(r"^IF\b.*\bTHEN\b", re.IGNORECASE | re.DOTALL)
# `- F1: <fact> (source: <where>; <YYYY-MM-DD>)`. The separator is a semicolon
# because sources are usually URLs and URLs contain commas often enough to matter.
FINDING = re.compile(
    r"^\s*[-*]\s*(F\d+)\s*[:.]\s*(.+?)\s*"
    r"\(source:\s*(.+?);\s*(\d{4}-\d{2}-\d{2})\s*\)\s*$"
)
# Deliberately looser than FINDING, so a bullet that means to be a finding but is
# malformed gets reported rather than silently skipped.
FINDING_LINE = re.compile(r"^\s*[-*]\s*F\d+\b")
FINDING_REF = re.compile(r"\bF\d+\b")
VERDICT_LINE = re.compile(r"^\*\*Verdict:\*\*\s*(\w+)", re.MULTILINE)
TASK = re.compile(
    r"^\s*[-*]\s*\[[ xX]\]\s*(T\d+)\s+(.+?)\s*"
    r"\(implements:\s*([^;]*);\s*depends on:\s*([^)]*)\)\s*$"
)
# A requirement with no verb of obligation is a wish, not a requirement.
SHALL = re.compile(r"\bSHALL\b")


class Report:
    """Collected findings. Errors fail the run; warnings are advisory."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def sections(text: str) -> dict[str, str]:
    """Map `## Heading` to its body, ignoring headings inside fenced blocks."""
    found: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    in_fence = False

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            if current is not None:
                found[current] = "\n".join(buffer).strip()
            current, buffer = line[3:].strip(), []
            continue
        buffer.append(line)

    if current is not None:
        found[current] = "\n".join(buffer).strip()
    return found


def detect_schema(present: dict[str, str]) -> str | None:
    for name, titles in SCHEMAS.items():
        if titles[1] in present:
            return name
    return None


def check_header(text: str, report: Report) -> None:
    head = text.split("\n## ", 1)[0]
    if not head.lstrip().startswith("# Implementation Brief"):
        report.error("the brief must open with the heading '# Implementation Brief'")
    for field in HEADER_FIELDS:
        if f"**{field}:**" not in head:
            report.error(f"header is missing the '{field}' field")


def check_structure(present: dict[str, str], schema: str, report: Report) -> None:
    expected = SCHEMAS[schema]
    for title in expected:
        if title not in present:
            report.error(f"missing section: '{title}'")
        elif not present[title]:
            report.error(f"section is empty: '{title}'")

    order = [t for t in present if t in expected]
    if order != [t for t in expected if t in present]:
        report.error(f"sections are out of order; expected {' -> '.join(expected)}")

    for title in present:
        if title not in expected:
            report.warn(f"unrecognised section for the {schema} schema: '{title}'")


def parse_requirements(body: str, prefix: str, report: Report) -> dict[str, str]:
    """Collect PREFIX-numbered requirements, checking syntax and numbering."""
    found: dict[str, str] = {}
    for line in body.splitlines():
        match = REQUIREMENT.match(line)
        if not match:
            continue
        ident, statement = match.group(1), match.group(2).strip()
        if not ident.startswith(prefix):
            continue
        if ident in found:
            report.error(f"duplicate requirement ID: {ident}")
        found[ident] = statement
        if not SHALL.search(statement):
            report.error(
                f"{ident} has no SHALL — rewrite it with a requirement template "
                f"(see reference/requirements-syntax.md): {statement[:60]!r}"
            )

    numbers = sorted(int(i[len(prefix):]) for i in found)
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        report.error(
            f"{prefix} numbering must run 1..{len(numbers)} with no gaps; found "
            + ", ".join(f"{prefix}{n}" for n in numbers)
        )
    return found


def check_criteria(body: str, requirements: set[str], report: Report) -> None:
    criteria: dict[str, set[str]] = {}
    covered: set[str] = set()
    unbracketed: list[str] = []

    for line in body.splitlines():
        match = CRITERION.match(line)
        if not match:
            continue
        ident, statement = match.group(1), match.group(2).strip()
        if ident in criteria:
            report.error(f"duplicate acceptance criterion ID: {ident}")

        prefix = COVERS.match(statement)
        if not prefix:
            unbracketed.append(ident)
            criteria[ident] = set()
            continue

        refs = set(ID_REF.findall(prefix.group(1)))
        if not refs:
            unbracketed.append(ident)
        for ref in sorted(refs - requirements):
            report.error(f"{ident} cites {ref}, which is not defined in the brief")
        criteria[ident] = refs
        covered |= refs & requirements

    if not criteria:
        report.error("no acceptance criteria found; expected a numbered AC1, AC2, ... list")
        return

    for ident in unbracketed:
        report.error(
            f"{ident} does not open with the requirement IDs it covers, e.g. "
            f"'{ident}: [FR2, FR5] ...'"
        )

    functional = {r for r in requirements if r.startswith("FR")}
    for ref in sorted(functional - covered, key=lambda r: int(r[2:])):
        report.error(f"{ref} is not covered by any acceptance criterion")


def check_assumptions(text: str, report: Report) -> None:
    if "[ASSUMPTION]" not in text:
        report.warn(
            "no [ASSUMPTION] markers found — unusual unless the user specified "
            "every choice explicitly"
        )


def check_tasks(text: str, requirements: set[str], report: Report) -> None:
    tasks: dict[str, set[str]] = {}
    order: list[int] = []
    covered: set[str] = set()
    lines = [l for l in text.splitlines() if l.lstrip().startswith(("- [", "* ["))]

    for line in lines:
        match = TASK.match(line)
        if not match:
            report.error(
                "task line does not parse; expected "
                "'- [ ] T1 Do the thing. (implements: FR1; depends on: none)': "
                f"{line.strip()[:70]!r}"
            )
            continue

        ident, _, implements, depends = match.groups()
        if ident in tasks:
            report.error(f"duplicate task ID: {ident}")
        number = int(ident[1:])
        order.append(number)

        refs = set(ID_REF.findall(implements))
        if not refs:
            report.error(f"{ident} implements nothing; cite the requirement IDs it covers")
        for ref in sorted(refs - requirements):
            report.error(f"{ident} implements {ref}, which is not defined in the brief")
        tasks[ident] = refs
        covered |= refs & requirements

        for dep in re.findall(r"\bT\d+\b", depends):
            if int(dep[1:]) >= number:
                report.error(
                    f"{ident} depends on {dep}, which is not an earlier task; "
                    "the list must be dependency-ordered"
                )
            elif dep not in tasks:
                report.error(f"{ident} depends on {dep}, which is not defined")
        if not re.search(r"\bT\d+\b|\bnone\b", depends, re.IGNORECASE):
            report.error(f"{ident} has an unreadable 'depends on' value: {depends.strip()!r}")

    if not tasks:
        report.error("no tasks found; expected a '- [ ] T1 ...' checklist")
        return

    if order != list(range(1, len(order) + 1)):
        report.error(
            f"task numbering must run T1..T{len(order)} in order with no gaps; found "
            + ", ".join(f"T{n}" for n in order)
        )

    functional = {r for r in requirements if r.startswith("FR")}
    for ref in sorted(functional - covered, key=lambda r: int(r[2:])):
        report.error(f"{ref} is not implemented by any task")


def source_key(source: str) -> str:
    """Collapse a citation to the thing that makes it independent — the host for a
    URL, the tracker or file for an internal reference. Six pages of one vendor's
    docs are one source, not six."""
    parts = urlsplit(source.strip())
    if parts.scheme in ("http", "https") and parts.netloc:
        return parts.netloc.lower().removeprefix("www.")
    return source.strip().split(":", 1)[0].lower() or source.strip().lower()


def is_public_url(source: str) -> bool:
    parts = urlsplit(source.strip())
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if host in LOCAL_HOSTNAMES:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global


def fetch_status(url: str, timeout: float = SOURCE_TIMEOUT) -> tuple[bool, str]:
    """Return (reachable, detail). Split apart from the reporting so the network
    boundary is one function and can be stubbed in tests."""
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "incipit-brief-check/1 (+citation verification)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, str(response.status)
    except urllib.error.HTTPError as exc:
        # Plenty of servers reject HEAD but serve GET; only a 4xx that isn't about
        # the method tells us the citation is dead.
        if exc.code in (403, 405, 501):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=request.headers),
                    timeout=timeout,
                ) as response:
                    return True, str(response.status)
            except Exception as inner:  # noqa: BLE001 - reported, not handled
                return False, f"HTTP {exc.code}, then {inner}"
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - urllib raises a wide range here
        return False, str(exc)


def verify_sources(citations: dict[str, str], report: Report) -> None:
    """Fetch every cited URL. A dead citation is an error; an unreachable one is a
    warning, because this cannot tell a removed page from a missing network."""
    for ident, url in sorted(citations.items(), key=lambda kv: int(kv[0][1:])):
        reachable, detail = fetch_status(url)
        if reachable:
            continue
        if detail.startswith("HTTP 4"):
            report.error(f"{ident} cites a dead URL ({detail}): {url}")
        else:
            report.warn(f"{ident} cites an unreachable URL ({detail}): {url}")


def check_research(text: str, report: Report,
                   citations: dict[str, str] | None = None) -> set[str]:
    """Validate research.md and return the finding IDs it defines. When `citations`
    is given, it is filled with the public URLs each finding cites."""
    head = text.split("\n## ", 1)[0]
    if not head.lstrip().startswith("# Research"):
        report.error("research must open with the heading '# Research'")
    for field in ("Idea", "Date"):
        if f"**{field}:**" not in head:
            report.error(f"research header is missing the '{field}' field")

    verdict = VERDICT_LINE.search(head)
    if not verdict:
        report.error(
            "research is missing a '**Verdict:** build|adopt|extend — <reason>' line"
        )
    elif verdict.group(1).lower() not in VERDICTS:
        report.error(
            f"research verdict must be one of {', '.join(VERDICTS)}; "
            f"found {verdict.group(1)!r}"
        )

    present = sections(text)
    for title in RESEARCH_SECTIONS:
        if title not in present:
            report.error(f"research is missing section: '{title}'")
        elif not present[title]:
            report.error(f"research section is empty: '{title}'")

    findings: dict[str, str] = {}
    sources: set[str] = set()
    today = dt.date.today()

    for title, body in present.items():
        for line in body.splitlines():
            match = FINDING.match(line)
            if not match:
                if FINDING_LINE.match(line):
                    report.error(
                        "finding is missing a well-formed citation; expected "
                        "'- F1: <fact> (source: <url or reference>; YYYY-MM-DD)': "
                        f"{line.strip()[:70]!r}"
                    )
                continue

            ident, _, source, date = match.groups()
            if ident in findings:
                report.error(f"duplicate finding ID: {ident}")
            findings[ident] = title
            sources.add(source_key(source))
            if citations is not None and is_public_url(source):
                citations[ident] = source.strip()

            try:
                looked_up = dt.date.fromisoformat(date)
            except ValueError:
                report.error(f"{ident} has an invalid date: {date}")
                continue
            if looked_up > today:
                report.error(f"{ident} is dated in the future: {date}")

    if not findings:
        report.error("no findings recorded; expected '- F1: ... (source: ...; date)' lines")
        return set()

    numbers = sorted(int(i[1:]) for i in findings)
    if numbers != list(range(1, len(numbers) + 1)):
        report.error(
            f"finding numbering must run F1..F{len(numbers)} with no gaps; found "
            + ", ".join(f"F{n}" for n in numbers)
        )

    if "Prior art" not in findings.values():
        report.error(
            "no finding under 'Prior art'; record what exists, or record the "
            "searches that turned up nothing"
        )

    if len(sources) < MIN_DISTINCT_SOURCES:
        report.warn(
            f"every finding traces to {len(sources)} distinct source(s); "
            "anything load-bearing wants two independent ones"
        )

    return set(findings)


def check(brief_path: Path, tasks_path: Path | None,
          research_path: Path | None = None, check_sources: bool = False) -> Report:
    report = Report()
    text = brief_path.read_text(encoding="utf-8")
    present = sections(text)

    schema = detect_schema(present)
    if schema is None:
        report.error(
            "cannot tell which schema this brief uses; it needs either a "
            "'## Functional Requirements' section (software) or a '## Requirements' "
            "section (generic)"
        )
        return report

    check_header(text, report)
    check_structure(present, schema, report)
    check_assumptions(text, report)

    titles = SCHEMAS[schema]
    functional = parse_requirements(present.get(titles[1], ""), "FR", report)
    nonfunctional = parse_requirements(present.get(titles[2], ""), "NFR", report)
    if not functional:
        report.error(f"no requirements found in '{titles[1]}'; expected FR1, FR2, ...")
    elif not any(UNWANTED.match(s) for s in functional.values()):
        report.error(
            "no requirement covers an error or edge path; add at least one using "
            "the 'IF <condition>, THEN ... SHALL ...' template"
        )

    requirements = set(functional) | set(nonfunctional)
    check_criteria(present.get("Acceptance Criteria", ""), requirements, report)

    if tasks_path is not None:
        check_tasks(tasks_path.read_text(encoding="utf-8"), requirements, report)

    if research_path is not None:
        citations: dict[str, str] = {}
        findings = check_research(research_path.read_text(encoding="utf-8"), report,
                                 citations)
        check_citations(text, findings, report)
        if check_sources:
            verify_sources(citations, report)

    return report


def check_citations(brief: str, findings: set[str], report: Report) -> None:
    """Tie the brief to the research both ways: a cited finding must exist, and a
    recorded finding that changed nothing was not worth recording."""
    if "**Research:**" not in brief.split("\n## ", 1)[0]:
        report.error("header is missing the 'Research' field pointing at research.md")

    cited = set(FINDING_REF.findall(brief))
    for ref in sorted(cited - findings, key=lambda r: int(r[1:])):
        report.error(f"the brief cites {ref}, which is not defined in the research")

    for ref in sorted(findings - cited, key=lambda r: int(r[1:])):
        report.warn(
            f"{ref} is not cited anywhere in the brief — it should have changed "
            "something, or it wasn't worth recording"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("brief", type=Path, help="path to brief.md")
    ap.add_argument("--tasks", type=Path, default=None, help="path to tasks.md")
    ap.add_argument("--research", type=Path, default=None, help="path to research.md")
    ap.add_argument("--verify-sources", action="store_true",
                    help="fetch every cited URL and fail on dead ones (needs network)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as failures")
    args = ap.parse_args()

    if args.verify_sources and args.research is None:
        print("error: --verify-sources needs --research", file=sys.stderr)
        return 2

    for path in (args.brief, args.tasks, args.research):
        if path is not None and not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 2

    report = check(args.brief, args.tasks, args.research, args.verify_sources)

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")

    if report.errors or (args.strict and report.warnings):
        total = len(report.errors) + (len(report.warnings) if args.strict else 0)
        print(f"\n{args.brief}: FAILED ({total} to fix)")
        return 1

    print(f"{args.brief}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
