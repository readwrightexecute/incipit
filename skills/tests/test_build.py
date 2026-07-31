"""Tests for the skill adapter generator (skills/build.py).

The point of the generator is that skills/dist is never hand-edited, so the
load-bearing test is the staleness check: if someone edits skills/src (or an
adapter copy) without rebuilding, CI fails instead of shipping a drifted skill.

Self-contained: these resolve paths from this file and import nothing from the
web app, so `skills/` can be lifted out of this repo and still verify itself.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent


def _load_build():
    spec = importlib.util.spec_from_file_location("skills_build", SKILLS / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_mod = _load_build()
MANIFEST = json.loads((SKILLS / "harnesses.json").read_text())


# --- the staleness guard ----------------------------------------------------

def test_dist_is_not_stale():
    """skills/dist must match what skills/src generates. If this fails, run
    `python3 skills/build.py`."""
    problems = build_mod.diff(build_mod.build(), build_mod.current())
    assert problems == [], "skills/dist is stale:\n  " + "\n  ".join(problems)


# --- source skill invariants ------------------------------------------------

@pytest.mark.parametrize("skill", MANIFEST["skills"])
def test_source_skill_has_required_frontmatter(skill):
    front, body = build_mod.split_frontmatter(
        (SKILLS / "src" / skill / "SKILL.md").read_text()
    )
    assert front["name"] == skill, "frontmatter name must match the directory"
    assert front["description"].strip()
    assert len(front["description"]) <= 1024
    assert body.strip()


@pytest.mark.parametrize("skill", MANIFEST["skills"])
def test_source_skill_name_is_a_valid_slug(skill):
    assert len(skill) <= 64
    assert skill == skill.lower()
    assert all(c.isalnum() or c == "-" for c in skill)


@pytest.mark.parametrize("skill", MANIFEST["skills"])
def test_skill_body_stays_under_500_lines(skill):
    """Progressive disclosure budget: detail belongs in reference/, not in the
    always-loaded body."""
    _, body = build_mod.split_frontmatter(
        (SKILLS / "src" / skill / "SKILL.md").read_text()
    )
    assert len(body.splitlines()) < 500


def test_relative_links_resolve_to_real_files():
    """A reference link that 404s is a silently broken skill."""
    for skill in MANIFEST["skills"]:
        skill_dir = SKILLS / "src" / skill
        text = (skill_dir / "SKILL.md").read_text()
        for target in build_mod.re.findall(r"\]\((reference/[^)]+)\)", text):
            assert (skill_dir / target).is_file(), f"{skill}: dead link to {target}"


# --- rendering --------------------------------------------------------------

def test_harness_frontmatter_is_merged_over_the_source():
    hermes = next(h for h in MANIFEST["harnesses"] if h["id"] == "hermes")
    rendered = build_mod.render_skill_md(
        "incipit",
        (SKILLS / "src" / "incipit" / "SKILL.md").read_text(),
        hermes["frontmatter"],
    )
    front, _ = rendered.split("\n---\n", 1)[0], None
    assert "version: 1.0.0" in front
    assert "platforms: [linux, macos, windows]" in front
    assert "name: incipit" in front  # source keys survive the merge


def test_bodies_are_identical_across_harnesses():
    """Harnesses may differ in frontmatter only. A body that diverges is the
    drift this generator exists to prevent."""
    tree = build_mod.build()
    bodies = {
        path.split("/", 1)[0]: content.split("\n---\n", 1)[1]
        for path, content in tree.items()
        if path.endswith("incipit/SKILL.md")
    }
    assert len(set(bodies.values())) == 1, f"bodies diverged across {sorted(bodies)}"


def test_agents_md_inlines_references_and_rewrites_links():
    document = build_mod.render_agents_md(MANIFEST["skills"], "preamble")
    assert "](reference/" not in document, "relative links can't work in one file"
    assert "## Requirement syntax" in document
    assert "](#requirement-syntax)" in document


def test_agents_md_rewrites_links_between_reference_files():
    """A reference file linking to a sibling by bare name would otherwise point at
    a file the single-document fallback doesn't have."""
    document = build_mod.render_agents_md(MANIFEST["skills"], "")
    assert "](requirements-syntax.md)" not in document


def test_agents_md_does_not_shift_headings_inside_code_fences():
    """The brief template is a fenced block whose `# Implementation Brief` is
    literal output, not document structure."""
    document = build_mod.render_agents_md(MANIFEST["skills"], "")
    assert "\n# Implementation Brief\n" in document


# --- yaml emitting ----------------------------------------------------------

def test_yaml_quotes_values_that_would_change_meaning():
    assert build_mod.yaml_scalar("plain text") == "plain text"
    assert build_mod.yaml_scalar("key: value") == '"key: value"'
    assert build_mod.yaml_scalar("- leading dash") == '"- leading dash"'
    assert build_mod.yaml_scalar("trailing # comment") == '"trailing # comment"'
    # A leading quote would start a quoted scalar; an interior one is plain-safe.
    assert build_mod.yaml_scalar('"leading quote') == '"\\"leading quote"'
    assert build_mod.yaml_scalar('says "this"') == 'says "this"'


@pytest.mark.parametrize(
    "value",
    [
        'ends in a quoted phrase like "this"',
        "key: value",
        "- leading dash",
        '"fully quoted"',
        "plain",
    ],
)
def test_frontmatter_survives_an_emit_parse_round_trip(value):
    """Emitting then re-parsing must return the original string, or descriptions
    silently corrupt on every rebuild."""
    emitted = "---\n" + "\n".join(build_mod.emit_yaml({"description": value})) + "\n---\nbody\n"
    front, _ = build_mod.split_frontmatter(emitted)
    assert front["description"] == value


def test_split_frontmatter_rejects_a_file_without_it():
    with pytest.raises(ValueError):
        build_mod.split_frontmatter("# No frontmatter here\n")
