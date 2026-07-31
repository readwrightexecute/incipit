"""Tests for the pure model-output parsers in app/wizard/flow.py.

These functions turn free-form LLM text into structured state mutations, so
their parsing behavior is correctness-critical and fully deterministic. No LLM
or network is involved — we call the parsers directly with constructed text.
"""

import pytest

from app.wizard import flow
from app.wizard.state import Section, Session


def _session(**kw) -> Session:
    s = Session(id="test", created=0.0)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _sections() -> list[Section]:
    return [
        Section(id="overview", title="Project Overview", instruction=""),
        Section(id="tech", title="Tech Constraints", instruction=""),
        Section(id="ux", title="User Experience", instruction=""),
    ]


# --- parse_questions --------------------------------------------------------

def test_parse_questions_basic_and_assumptions():
    text = (
        "1. What database should we use?\n"
        "[ASSUMPTION] PostgreSQL\n"
        "2) Which web framework?\n"
        "[ASSUMPTION]: FastAPI\n"
        "garbage line that is not a question\n"
        "3. Any auth requirements?\n"
    )
    qas = flow.parse_questions(text)
    assert [q.question for q in qas] == [
        "What database should we use?",
        "Which web framework?",
        "Any auth requirements?",
    ]
    assert qas[0].assumption == "PostgreSQL"
    # The "[ASSUMPTION]:" prefix punctuation/space is stripped.
    assert qas[1].assumption == "FastAPI"
    # Question with no following assumption line keeps the empty default.
    assert qas[2].assumption == ""


def test_parse_questions_assumption_before_any_question_is_ignored():
    # No `current` QA exists yet, so a leading assumption line is dropped.
    qas = flow.parse_questions("[ASSUMPTION] orphan default\n1. Real question?\n")
    assert len(qas) == 1
    assert qas[0].question == "Real question?"
    assert qas[0].assumption == ""


def test_parse_questions_numbered_line_with_inline_assumption_is_not_a_question():
    # A numbered line that itself contains [ASSUMPTION] is not treated as a new
    # question (the guard `"[ASSUMPTION]" not in line`), and with no prior
    # question it attaches to nothing.
    qas = flow.parse_questions("1. [ASSUMPTION] inline default\n")
    assert qas == []


@pytest.mark.parametrize("text", ["", "   \n\t\n", "no numbers here\njust prose"])
def test_parse_questions_blank_or_garbage_returns_empty(text):
    # The failure path: nothing parseable yields an empty list (run_clarify is
    # what turns this into a GenerationError, not parse_questions itself).
    assert flow.parse_questions(text) == []


def test_parse_questions_handles_paren_delimiter():
    qas = flow.parse_questions("1) First?\n2) Second?\n")
    assert [q.question for q in qas] == ["First?", "Second?"]


# --- _resolve_section -------------------------------------------------------

def test_resolve_section_empty_returns_none():
    assert flow._resolve_section("", _sections()) is None


def test_resolve_section_exact_id():
    assert flow._resolve_section("overview", _sections()) == "overview"


def test_resolve_section_exact_id_case_insensitive():
    assert flow._resolve_section("OVERVIEW", _sections()) == "overview"


def test_resolve_section_exact_title():
    assert flow._resolve_section("Project Overview", _sections()) == "overview"


def test_resolve_section_title_substring_tier():
    # "constraints" is not an id, but is a substring of the "Tech Constraints"
    # title → second tier match.
    assert flow._resolve_section("constraints", _sections()) == "tech"


def test_resolve_section_title_reverse_substring_tier():
    # The title is a substring of the raw id → also a second-tier match.
    assert flow._resolve_section("the tech constraints section", _sections()) == "tech"


def test_resolve_section_id_substring_third_tier():
    # No id/title equality or title-substring match, but the section id "ux" is
    # a substring of the raw key → third tier.
    assert flow._resolve_section("uxbar", _sections()) == "ux"


def test_resolve_section_no_match_returns_none():
    assert flow._resolve_section("completely unrelated", _sections()) is None


def test_resolve_section_documents_surprising_substring_collision():
    # CURRENT BEHAVIOR (documented, not endorsed): the third tier matches when a
    # section id is a substring of the raw key. "data" is a substring of
    # "database", so a model emitting SECTION: database resolves to the "data"
    # section even though the words are unrelated.
    secs = [
        Section(id="api", title="API Design", instruction=""),
        Section(id="data", title="Data Model", instruction=""),
    ]
    assert flow._resolve_section("database", secs) == "data"


@pytest.mark.xfail(
    reason="Latent bug: the substring tiers in _resolve_section can match an "
    "unrelated section (e.g. raw_id 'database' -> section id 'data'). This "
    "xfail documents the behavior we'd arguably prefer; app code is unchanged.",
    strict=False,
)
def test_resolve_section_should_not_collide_on_unrelated_substring():
    secs = [
        Section(id="api", title="API Design", instruction=""),
        Section(id="data", title="Data Model", instruction=""),
    ]
    assert flow._resolve_section("database", secs) is None


# --- _parse_changes ---------------------------------------------------------

def test_parse_changes_well_formed_single_block():
    s = _session(sections=_sections())
    raw = (
        "SECTION: overview\n"
        "CHANGE: Tighten the opening paragraph.\n"
        "WHY: It is too verbose.\n"
    )
    changes = flow._parse_changes(s, raw)
    assert len(changes) == 1
    c = changes[0]
    assert c.section_id == "overview"
    assert c.section_title == "Project Overview"
    assert c.instruction == "Tighten the opening paragraph."
    assert c.rationale == "It is too verbose."


def test_parse_changes_multiple_blocks_separated_by_dashes():
    s = _session(sections=_sections())
    raw = (
        "SECTION: overview\n"
        "CHANGE: Do X.\n"
        "---\n"
        "SECTION: tech\n"
        "CHANGE: Do Y.\n"
    )
    changes = flow._parse_changes(s, raw)
    assert [c.section_id for c in changes] == ["overview", "tech"]
    assert [c.instruction for c in changes] == ["Do X.", "Do Y."]


def test_parse_changes_skips_block_without_change():
    s = _session(sections=_sections())
    raw = "SECTION: overview\nWHY: missing change line\n"
    assert flow._parse_changes(s, raw) == []


def test_parse_changes_skips_unresolvable_section():
    s = _session(sections=_sections())
    raw = "SECTION: nonexistent-thing-xyz\nCHANGE: Do something.\n"
    assert flow._parse_changes(s, raw) == []


@pytest.mark.parametrize("raw", ["", "NO CHANGES", "   \n---\n   "])
def test_parse_changes_empty_or_no_changes_returns_empty(raw):
    s = _session(sections=_sections())
    assert flow._parse_changes(s, raw) == []


# --- _parse_qa_changes ------------------------------------------------------

def test_parse_qa_changes_add_question():
    s = _session(qas=[])
    raw = (
        "ADD_QUESTION: What about authentication?\n"
        "ASSUMPTION: OAuth2\n"
        "WHY: Security matters.\n"
    )
    changes = flow._parse_qa_changes(s, raw)
    assert len(changes) == 1
    c = changes[0]
    assert c.kind == "add_question"
    assert c.question == "What about authentication?"
    assert c.assumption == "OAuth2"
    assert c.rationale == "Security matters."


def test_parse_qa_changes_suggest_answer_in_range():
    from app.wizard.state import QA

    s = _session(qas=[QA(question="Q1", assumption=""), QA(question="Q2", assumption="")])
    raw = (
        "SUGGEST_ANSWER: 2\n"
        "ANSWER: Use PostgreSQL.\n"
        "WHY: It is the standard.\n"
    )
    changes = flow._parse_qa_changes(s, raw)
    assert len(changes) == 1
    c = changes[0]
    assert c.kind == "suggest_answer"
    assert c.target == 1  # 1-based "2" -> 0-based index 1
    assert c.answer == "Use PostgreSQL."


def test_parse_qa_changes_suggest_answer_out_of_range_skipped():
    from app.wizard.state import QA

    s = _session(qas=[QA(question="Q1", assumption="")])
    raw = "SUGGEST_ANSWER: 99\nANSWER: irrelevant\n"
    assert flow._parse_qa_changes(s, raw) == []


def test_parse_qa_changes_suggest_answer_without_index_skipped():
    from app.wizard.state import QA

    s = _session(qas=[QA(question="Q1", assumption="")])
    raw = "SUGGEST_ANSWER: this question\nANSWER: irrelevant\n"
    assert flow._parse_qa_changes(s, raw) == []


def test_parse_qa_changes_add_question_with_empty_value_skipped():
    s = _session(qas=[])
    raw = "ADD_QUESTION:\nWHY: nothing\n"
    assert flow._parse_qa_changes(s, raw) == []


@pytest.mark.parametrize("raw", ["", "NO CHANGES", "   "])
def test_parse_qa_changes_empty_returns_empty(raw):
    s = _session(qas=[])
    assert flow._parse_qa_changes(s, raw) == []


def test_parse_qa_changes_mixed_blocks():
    from app.wizard.state import QA

    s = _session(qas=[QA(question="Q1", assumption=""), QA(question="Q2", assumption="")])
    raw = (
        "ADD_QUESTION: New one?\n"
        "ASSUMPTION: default\n"
        "---\n"
        "SUGGEST_ANSWER: 1\n"
        "ANSWER: An answer.\n"
    )
    changes = flow._parse_qa_changes(s, raw)
    assert [c.kind for c in changes] == ["add_question", "suggest_answer"]


# --- _parse_facilitator -----------------------------------------------------

def test_parse_facilitator_consensus():
    raw = "We all agree the spec is solid.\nACTION: CONSENSUS\n"
    say, action, next_ids = flow._parse_facilitator(raw)
    assert say == "We all agree the spec is solid."
    assert action == "CONSENSUS"
    assert next_ids == []


def test_parse_facilitator_next_with_valid_ids():
    raw = "Let's hear more.\nACTION: NEXT pm, architect\n"
    say, action, next_ids = flow._parse_facilitator(raw)
    assert say == "Let's hear more."
    assert action == "NEXT"
    assert next_ids == ["pm", "architect"]


def test_parse_facilitator_next_filters_unknown_ids():
    # Unknown persona ids are dropped; "pm" is valid, "bogus" is not.
    say, action, next_ids = flow._parse_facilitator("hmm\nACTION: NEXT pm bogus\n")
    assert action == "NEXT"
    assert next_ids == ["pm"]


def test_parse_facilitator_next_with_no_valid_ids_becomes_consensus():
    say, action, next_ids = flow._parse_facilitator("hmm\nACTION: NEXT nobody\n")
    assert action == "CONSENSUS"
    assert next_ids == []


def test_parse_facilitator_no_action_line_defaults_to_consensus():
    raw = "Just some discussion with no action directive."
    say, action, next_ids = flow._parse_facilitator(raw)
    assert say == "Just some discussion with no action directive."
    assert action == "CONSENSUS"
    assert next_ids == []


# --- assemble_final ---------------------------------------------------------

def test_assemble_final_structure():
    s = _session(
        idea="A todo app",
        project_type="new",
        stakes="serious",
        form_factor="web app",
        sections=[
            Section(id="overview", title="Project Overview", instruction="", content="It tracks todos."),
            Section(id="tech", title="Tech Constraints", instruction="", content="Python + FastAPI."),
        ],
    )
    out = flow.assemble_final(s)
    assert out.startswith("# Implementation Brief")
    assert "**Project idea (verbatim from the author):** A todo app" in out
    assert "**Form factor:** web app" in out
    assert "## Project Overview" in out
    assert "It tracks todos." in out
    assert "## Tech Constraints" in out
    assert "Python + FastAPI." in out
    # The stakes/project hints come from the module-level lookup tables.
    assert flow.STAKES_HINTS["serious"] in out
    assert flow.PROJECT_TYPE_HINTS["new"] in out


def test_assemble_final_existing_project_includes_repo_line():
    s = _session(
        idea="X",
        project_type="existing",
        stakes="serious",
        form_factor="CLI tool",
        repo_url="https://github.com/owner/repo",
        sections=[],
    )
    out = flow.assemble_final(s)
    assert "**Existing repository:** https://github.com/owner/repo" in out


def test_assemble_final_new_project_omits_repo_line():
    s = _session(
        idea="X", project_type="new", stakes="serious", form_factor="CLI tool",
        repo_url="https://github.com/owner/repo", sections=[],
    )
    out = flow.assemble_final(s)
    # repo_url is set but project_type is "new", so the repo line is omitted.
    assert "Existing repository" not in out
