"""Tests for the brief verification gate (src/incipit/scripts/brief_check.py).

The gate exists because an agent rereading its own brief is an unreliable judge of
whether it followed the rules. That only holds if the gate itself is reliable, so
every rule it enforces gets a failing fixture here — a checker that silently passes
a broken brief is worse than no checker, since the flow now trusts it.

Self-contained: paths resolve from this file and nothing from the web app is
imported, so `skills/` can be lifted out of this repo and still verify itself.
"""

import importlib.util
import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent
SCRIPT = SKILLS / "src" / "incipit" / "scripts" / "brief_check.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("brief_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bc = _load_checker()

GOOD_BRIEF = """# Implementation Brief

You are implementing the following project.

**Project idea (verbatim from the author):** a thing that saves my notes
**Project type:** new — greenfield
**Stakes:** hobby — personal/hobby project
**Form factor:** CLI tool

## Goals & Background

- Capture notes fast.

Background paragraph explaining why.

## Functional Requirements

FR1: THE SYSTEM SHALL append a note to a plain-text file.
FR2: WHEN the user passes --list, THE SYSTEM SHALL print all notes.
FR3: IF the notes file is unreadable, THEN THE SYSTEM SHALL exit with an error.

## Non-Functional Requirements

NFR1: THE SYSTEM SHALL start in under 200ms. [ASSUMPTION]

## Tech Constraints & Stack

- Python 3.11, standard library only. [ASSUMPTION]

## Acceptance Criteria

AC1: [FR1] Done when the note appears at the end of the file.
AC2: [FR2] Done when --list prints every stored note.
AC3: [FR3] Given an unreadable file, when the tool runs, then it exits non-zero.

## Out of Scope

- Sync.
"""

GOOD_RESEARCH = """# Research

**Idea:** a CLI that saves notes
**Date:** 2026-08-01
**Verdict:** build — existing note tools all require a GUI or a sync account.

## Prior art

- F1: jrnl covers CLI journalling but assumes a git-backed store. (source: https://jrnl.sh/en/stable/; 2026-08-01)
- F2: No stdlib-only note CLI on PyPI; searched "note cli". (source: https://pypi.org/search/?q=note+cli; 2026-08-01)

## Approach

- F3: Appends under PIPE_BUF are atomic on POSIX. (source: https://man7.org/linux/man-pages/man2/write.2.html; 2026-08-01)

## Pitfalls

- F4: jrnl's store corrupts on concurrent writes. (source: https://github.com/jrnl-org/jrnl/issues/1010; 2026-08-01)

## External constraints

- F5: Python 3.11 is the oldest release still receiving fixes. (source: https://devguide.python.org/versions/; 2026-08-01)

## Open questions

- None.
"""

GOOD_TASKS = """# Tasks

## Phase 1 — Foundation

- [ ] T1 Create the CLI entry point. (implements: NFR1; depends on: none)
- [ ] T2 Append notes to the notes file. (implements: FR1; depends on: T1)

## Phase 2 — Read path

- [ ] T3 Implement the --list flag. (implements: FR2; depends on: T2)
- [ ] T4 Handle an unreadable notes file. (implements: FR3; depends on: T2)
"""


# A brief that cites every finding, as one written after the research would.
CITING_BRIEF = (GOOD_BRIEF
                .replace("**Form factor:** CLI tool",
                         "**Form factor:** CLI tool\n**Research:** research.md")
                .replace("Background paragraph explaining why.",
                         "CLI journals assume a git store (F1); nothing stdlib-only "
                         "exists (F2).")
                .replace("- Python 3.11, standard library only. [ASSUMPTION]",
                         '- Python 3.11 (F5), standard library only. [ASSUMPTION]\n'
                         '- Append with mode="a" (F3); avoid the corruption in (F4).'))


def run(tmp_path, brief=GOOD_BRIEF, tasks=None, research=None, check_sources=False):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    paths = []
    for name, content in (("tasks.md", tasks), ("research.md", research)):
        if content is None:
            paths.append(None)
            continue
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)

    return bc.check(brief_path, paths[0], paths[1], check_sources)


def errors(tmp_path, **kwargs):
    return "\n".join(run(tmp_path, **kwargs).errors)


def research_errors(tmp_path, research):
    """Research findings only, with a brief that cites all five."""
    return errors(tmp_path, brief=CITING_BRIEF, research=research)


# --- the happy path ---------------------------------------------------------

def test_a_well_formed_brief_passes(tmp_path):
    report = run(tmp_path)
    assert report.errors == []


def test_a_well_formed_brief_and_task_list_pass(tmp_path):
    report = run(tmp_path, tasks=GOOD_TASKS)
    assert report.errors == []


def test_the_generic_schema_passes_too(tmp_path):
    """Non-software briefs use different section titles and a different actor."""
    brief = (GOOD_BRIEF
             .replace("## Functional Requirements", "## Requirements")
             .replace("## Non-Functional Requirements", "## Quality Bar")
             .replace("## Tech Constraints & Stack", "## Resources & Constraints")
             .replace("THE SYSTEM SHALL", "THE PROCESS SHALL"))
    assert run(tmp_path, brief=brief).errors == []


# --- structure --------------------------------------------------------------

def test_a_missing_section_fails(tmp_path):
    brief = GOOD_BRIEF.replace("## Out of Scope\n\n- Sync.\n", "")
    assert "missing section: 'Out of Scope'" in errors(tmp_path, brief=brief)


def test_an_empty_section_fails(tmp_path):
    brief = GOOD_BRIEF.replace("## Out of Scope\n\n- Sync.\n", "## Out of Scope\n\n")
    assert "section is empty: 'Out of Scope'" in errors(tmp_path, brief=brief)


def test_sections_out_of_order_fail(tmp_path):
    swapped = (GOOD_BRIEF
               .replace("## Acceptance Criteria", "@@")
               .replace("## Tech Constraints & Stack", "## Acceptance Criteria")
               .replace("@@", "## Tech Constraints & Stack"))
    assert "out of order" in errors(tmp_path, brief=swapped)


def test_a_missing_header_field_fails(tmp_path):
    brief = GOOD_BRIEF.replace("**Form factor:** CLI tool\n", "")
    assert "missing the 'Form factor' field" in errors(tmp_path, brief=brief)


def test_an_unrecognised_schema_fails(tmp_path):
    brief = GOOD_BRIEF.replace("## Functional Requirements", "## Stuff It Does")
    assert "cannot tell which schema" in errors(tmp_path, brief=brief)


def test_headings_inside_code_fences_are_not_sections(tmp_path):
    """The brief template itself contains a fenced `## Goals & Background`."""
    brief = GOOD_BRIEF + "\n```\n## Not A Real Section\n```\n"
    report = run(tmp_path, brief=brief)
    assert report.errors == []
    assert not any("Not A Real Section" in w for w in report.warnings)


# --- requirement syntax -----------------------------------------------------

def test_a_requirement_without_shall_fails(tmp_path):
    brief = GOOD_BRIEF.replace(
        "FR1: THE SYSTEM SHALL append a note to a plain-text file.",
        "FR1: The app should be fast.",
    )
    assert "FR1 has no SHALL" in errors(tmp_path, brief=brief)


def test_a_gap_in_requirement_numbering_fails(tmp_path):
    brief = GOOD_BRIEF.replace("FR3:", "FR7:").replace("[FR3]", "[FR7]")
    assert "FR numbering must run 1..3" in errors(tmp_path, brief=brief)


def test_a_duplicate_requirement_id_fails(tmp_path):
    brief = GOOD_BRIEF.replace("FR2: WHEN", "FR1: WHEN")
    assert "duplicate requirement ID: FR1" in errors(tmp_path, brief=brief)


def test_no_requirements_at_all_fails(tmp_path):
    brief = GOOD_BRIEF.replace("FR1:", "x:").replace("FR2:", "y:").replace("FR3:", "z:")
    assert "no requirements found" in errors(tmp_path, brief=brief)


def test_nfr_is_not_mistaken_for_fr(tmp_path):
    """`NFR1` must not be parsed as an `FR` with a stray leading N."""
    report = run(tmp_path)
    assert report.errors == []


# --- acceptance criteria ----------------------------------------------------

def test_a_criterion_without_a_bracketed_reference_fails(tmp_path):
    brief = GOOD_BRIEF.replace("AC1: [FR1] Done when", "AC1: Done when")
    assert "AC1 does not open with the requirement IDs" in errors(tmp_path, brief=brief)


def test_a_criterion_citing_an_unknown_requirement_fails(tmp_path):
    brief = GOOD_BRIEF.replace("AC1: [FR1]", "AC1: [FR9]")
    assert "AC1 cites FR9, which is not defined" in errors(tmp_path, brief=brief)


def test_an_uncovered_requirement_fails(tmp_path):
    brief = GOOD_BRIEF.replace(
        "AC2: [FR2] Done when --list prints every stored note.\n", ""
    )
    assert "FR2 is not covered by any acceptance criterion" in errors(tmp_path, brief=brief)


def test_a_brief_with_no_unwanted_behaviour_requirement_fails(tmp_path):
    """Coverage of the error path is checked through the IF/THEN template rather
    than by sniffing prose for words like "invalid"."""
    brief = GOOD_BRIEF.replace(
        "FR3: IF the notes file is unreadable, THEN THE SYSTEM SHALL exit with an error.",
        "FR3: THE SYSTEM SHALL print a message on exit.",
    )
    assert "no requirement covers an error or edge path" in errors(tmp_path, brief=brief)


def test_a_duplicate_criterion_id_fails(tmp_path):
    brief = GOOD_BRIEF.replace("AC2: [FR2]", "AC1: [FR2]")
    assert "duplicate acceptance criterion ID: AC1" in errors(tmp_path, brief=brief)


# --- assumptions ------------------------------------------------------------

def test_a_brief_with_no_assumptions_warns_but_passes(tmp_path):
    brief = GOOD_BRIEF.replace(" [ASSUMPTION]", "")
    report = run(tmp_path, brief=brief)
    assert report.errors == []
    assert any("[ASSUMPTION]" in w for w in report.warnings)


# --- tasks ------------------------------------------------------------------

def test_an_unparseable_task_line_fails(tmp_path):
    tasks = GOOD_TASKS.replace(
        "- [ ] T3 Implement the --list flag. (implements: FR2; depends on: T2)",
        "- [ ] T3 Implement the --list flag.",
    )
    assert "does not parse" in errors(tmp_path, tasks=tasks)


def test_a_forward_dependency_fails(tmp_path):
    tasks = GOOD_TASKS.replace(
        "- [ ] T2 Append notes to the notes file. (implements: FR1; depends on: T1)",
        "- [ ] T2 Append notes to the notes file. (implements: FR1; depends on: T4)",
    )
    assert "not an earlier task" in errors(tmp_path, tasks=tasks)


def test_a_task_citing_an_unknown_requirement_fails(tmp_path):
    tasks = GOOD_TASKS.replace("(implements: FR2;", "(implements: FR9;")
    assert "T3 implements FR9" in errors(tmp_path, tasks=tasks)


def test_a_requirement_no_task_implements_fails(tmp_path):
    tasks = GOOD_TASKS.replace(
        "- [ ] T4 Handle an unreadable notes file. (implements: FR3; depends on: T2)\n", ""
    )
    assert "FR3 is not implemented by any task" in errors(tmp_path, tasks=tasks)


def test_a_gap_in_task_numbering_fails(tmp_path):
    tasks = GOOD_TASKS.replace("T4 Handle", "T9 Handle")
    assert "task numbering must run T1..T4" in errors(tmp_path, tasks=tasks)


def test_a_completed_checkbox_still_parses(tmp_path):
    """A task list is meant to be ticked off as work proceeds."""
    tasks = GOOD_TASKS.replace("- [ ] T1", "- [x] T1")
    assert run(tmp_path, tasks=tasks).errors == []


def test_an_empty_task_list_fails(tmp_path):
    assert "no tasks found" in errors(tmp_path, tasks="# Tasks\n\nNothing yet.\n")


# --- research ---------------------------------------------------------------

def test_a_well_formed_research_file_passes(tmp_path):
    report = run(tmp_path, brief=CITING_BRIEF, research=GOOD_RESEARCH)
    assert report.errors == []
    assert report.warnings == []


def test_research_is_optional(tmp_path):
    """A brief checked on its own must not be forced to carry a Research header."""
    assert run(tmp_path).errors == []


def test_a_brief_with_research_must_link_to_it(tmp_path):
    assert "missing the 'Research' field" in errors(
        tmp_path, brief=GOOD_BRIEF, research=GOOD_RESEARCH
    )


@pytest.mark.parametrize("verdict", ["build", "adopt", "extend"])
def test_every_verdict_is_accepted(tmp_path, verdict):
    research = GOOD_RESEARCH.replace("**Verdict:** build", f"**Verdict:** {verdict}")
    assert research_errors(tmp_path, research) == ""


def test_an_unknown_verdict_fails(tmp_path):
    research = GOOD_RESEARCH.replace("**Verdict:** build", "**Verdict:** maybe")
    assert "verdict must be one of" in research_errors(tmp_path, research)


def test_a_missing_verdict_fails(tmp_path):
    research = "\n".join(l for l in GOOD_RESEARCH.splitlines()
                         if not l.startswith("**Verdict:**"))
    assert "missing a '**Verdict:**" in research_errors(tmp_path, research)


def test_a_missing_research_section_fails(tmp_path):
    research = GOOD_RESEARCH.replace("## Pitfalls", "## Gotchas")
    assert "research is missing section: 'Pitfalls'" in research_errors(tmp_path, research)


def test_an_empty_open_questions_section_fails(tmp_path):
    """Open questions feed the clarifying step, so a blank one is a broken handoff."""
    research = GOOD_RESEARCH.replace("## Open questions\n\n- None.\n",
                                     "## Open questions\n\n")
    assert "research section is empty: 'Open questions'" in research_errors(tmp_path, research)


def test_a_finding_without_a_citation_fails(tmp_path):
    research = GOOD_RESEARCH.replace(
        "- F3: Appends under PIPE_BUF are atomic on POSIX. "
        "(source: https://man7.org/linux/man-pages/man2/write.2.html; 2026-08-01)",
        "- F3: Appends under PIPE_BUF are atomic on POSIX.",
    )
    assert "missing a well-formed citation" in research_errors(tmp_path, research)


def test_a_malformed_finding_bullet_is_not_silently_skipped(tmp_path):
    """A finding that loses its colon must be reported, not ignored."""
    research = GOOD_RESEARCH.replace("- F4: jrnl's store", "- F4 jrnl's store")
    assert "missing a well-formed citation" in research_errors(tmp_path, research)


def test_a_citation_dated_in_the_future_fails(tmp_path):
    research = GOOD_RESEARCH.replace("issues/1010; 2026-08-01",
                                     "issues/1010; 2099-01-01")
    assert "dated in the future" in research_errors(tmp_path, research)


def test_an_invalid_date_fails(tmp_path):
    research = GOOD_RESEARCH.replace("versions/; 2026-08-01", "versions/; 2026-13-45")
    assert "invalid date" in research_errors(tmp_path, research)


def test_a_gap_in_finding_numbering_fails(tmp_path):
    research = GOOD_RESEARCH.replace("- F5:", "- F9:")
    assert "finding numbering must run F1..F5" in research_errors(tmp_path, research)


def test_a_duplicate_finding_id_fails(tmp_path):
    research = GOOD_RESEARCH.replace("- F2:", "- F1:")
    assert "duplicate finding ID: F1" in research_errors(tmp_path, research)


def test_research_with_no_prior_art_finding_fails(tmp_path):
    """Whether the thing already exists is the question research is for."""
    research = GOOD_RESEARCH.replace(
        "- F1: jrnl covers CLI journalling but assumes a git-backed store. "
        "(source: https://jrnl.sh/en/stable/; 2026-08-01)\n", ""
    ).replace(
        "- F2: No stdlib-only note CLI on PyPI; searched \"note cli\". "
        "(source: https://pypi.org/search/?q=note+cli; 2026-08-01)",
        "Nothing comparable turned up.",
    )
    assert "no finding under 'Prior art'" in research_errors(tmp_path, research)


def test_a_brief_citing_an_unknown_finding_fails(tmp_path):
    brief = CITING_BRIEF.replace("(F5)", "(F42)")
    assert "cites F42, which is not defined in the research" in errors(
        tmp_path, brief=brief, research=GOOD_RESEARCH
    )


def test_a_finding_the_brief_never_cites_warns(tmp_path):
    brief = CITING_BRIEF.replace(' (F4)', "")
    report = run(tmp_path, brief=brief, research=GOOD_RESEARCH)
    assert report.errors == []
    assert any("F4 is not cited" in w for w in report.warnings)


def test_single_source_research_warns(tmp_path):
    research = re.sub(r"\(source: [^;]+;", "(source: https://jrnl.sh/x;", GOOD_RESEARCH)
    report = run(tmp_path, brief=CITING_BRIEF, research=research)
    assert report.errors == []
    assert any("distinct source" in w for w in report.warnings)


def test_pages_on_one_host_count_as_one_source(tmp_path):
    assert bc.source_key("https://www.jrnl.sh/a/b?c=d") == "jrnl.sh"
    assert bc.source_key("https://jrnl.sh/other") == "jrnl.sh"
    assert bc.source_key("repo:app/auth.py:40") == "repo"
    assert bc.source_key("PROJ-412") == "proj-412"


# --- source verification ----------------------------------------------------
#
# The network boundary is bc.fetch_status and nothing else, so these stub it. No
# test in this file may touch the network.

def stub_fetch(monkeypatch, outcomes):
    """Map URL substring -> (reachable, detail). Anything unmatched is a 200."""
    seen: list[str] = []

    def fake(url, timeout=None):
        seen.append(url)
        for fragment, outcome in outcomes.items():
            if fragment in url:
                return outcome
        return True, "200"

    monkeypatch.setattr(bc, "fetch_status", fake)
    return seen


def test_sources_are_not_fetched_unless_asked(tmp_path, monkeypatch):
    seen = stub_fetch(monkeypatch, {})
    run(tmp_path, brief=CITING_BRIEF, research=GOOD_RESEARCH)
    assert seen == [], "citation checking must stay offline by default"


def test_every_cited_url_is_fetched_when_asked(tmp_path, monkeypatch):
    seen = stub_fetch(monkeypatch, {})
    report = run(tmp_path, brief=CITING_BRIEF, research=GOOD_RESEARCH,
                 check_sources=True)
    assert report.errors == []
    assert len(seen) == 5


def test_a_dead_url_is_an_error(tmp_path, monkeypatch):
    stub_fetch(monkeypatch, {"jrnl.sh": (False, "HTTP 404")})
    assert "F1 cites a dead URL (HTTP 404)" in errors(
        tmp_path, brief=CITING_BRIEF, research=GOOD_RESEARCH, check_sources=True
    )


def test_an_unreachable_url_is_only_a_warning(tmp_path, monkeypatch):
    """Being offline must not be reported as a bad citation."""
    stub_fetch(monkeypatch, {"jrnl.sh": (False, "<urlopen error [Errno 8]>")})
    report = run(tmp_path, brief=CITING_BRIEF, research=GOOD_RESEARCH,
                 check_sources=True)
    assert report.errors == []
    assert any("unreachable URL" in w for w in report.warnings)


def test_internal_references_are_never_fetched(tmp_path, monkeypatch):
    seen = stub_fetch(monkeypatch, {})
    research = GOOD_RESEARCH.replace("https://jrnl.sh/en/stable/", "PROJ-412")
    run(tmp_path, brief=CITING_BRIEF, research=research, check_sources=True)
    assert all(url.startswith("http") for url in seen)
    assert len(seen) == 4


@pytest.mark.parametrize(
    "source, public",
    [
        ("https://example.com/a", True),
        ("http://example.com", True),
        ("https://localhost/x", False),
        ("http://127.0.0.1:8000/x", False),
        ("http://192.168.1.10/x", False),
        ("http://[::1]/x", False),
        ("PROJ-412", False),
        ("repo:app/auth.py:40", False),
        ("file:///etc/passwd", False),
    ],
)
def test_only_public_http_urls_are_treated_as_fetchable(source, public):
    """A citation pointing at loopback or a private range would make this script
    probe its own network, and isn't something a reader could open anyway."""
    assert bc.is_public_url(source) is public


def test_verify_sources_requires_research(tmp_path, monkeypatch):
    path = tmp_path / "brief.md"
    path.write_text(GOOD_BRIEF, encoding="utf-8")
    monkeypatch.setattr("sys.argv",
                        ["brief_check.py", str(path), "--verify-sources"])
    assert bc.main() == 2


# --- exit status ------------------------------------------------------------

def test_strict_mode_turns_warnings_into_failure(tmp_path, monkeypatch, capsys):
    path = tmp_path / "brief.md"
    path.write_text(GOOD_BRIEF.replace(" [ASSUMPTION]", ""), encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["brief_check.py", str(path)])
    assert bc.main() == 0

    monkeypatch.setattr("sys.argv", ["brief_check.py", str(path), "--strict"])
    assert bc.main() == 1


def test_a_missing_file_is_distinguished_from_a_failing_brief(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["brief_check.py", str(tmp_path / "nope.md")])
    assert bc.main() == 2


@pytest.mark.parametrize("prefix", ["FR", "NFR"])
def test_requirements_are_found_with_list_markers(tmp_path, prefix):
    """Authors bullet these lists as often as they leave them bare."""
    body = f"- {prefix}1: THE SYSTEM SHALL do the thing.\n"
    found = bc.parse_requirements(body, prefix, bc.Report())
    assert f"{prefix}1" in found
