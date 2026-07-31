"""Tests for the trigger evaluation set (skills/eval/triggers.json).

A skill that never fires is almost always a description problem, and the only way
to find out is to try phrasings the description wasn't written against. Whether a
prompt actually triggers a skill can only be checked against a live host, so what
is enforced here is that the eval set stays well-formed and covers every skill —
enough that a description change can't quietly ship without prompts to test it.
"""

import json
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent
TRIGGERS = json.loads((SKILLS / "eval" / "triggers.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((SKILLS / "harnesses.json").read_text(encoding="utf-8"))

CASES = {k: v for k, v in TRIGGERS.items() if not k.startswith("_")}


def test_every_shipped_skill_has_an_eval_entry():
    assert sorted(CASES) == sorted(MANIFEST["skills"])


@pytest.mark.parametrize("skill", sorted(CASES))
def test_each_skill_has_at_least_five_of_each_case(skill):
    """Five and five is the smallest set that catches both an over-narrow
    description and an over-broad one."""
    case = CASES[skill]
    assert len(case["should_trigger"]) >= 5
    assert len(case["near_miss"]) >= 5


@pytest.mark.parametrize("skill", sorted(CASES))
def test_near_misses_are_explained(skill):
    """An unexplained near miss can't be acted on when it starts failing."""
    for miss in CASES[skill]["near_miss"]:
        assert miss["prompt"].strip()
        assert miss["why"].strip()
        assert "expected" in miss, "state the skill that should fire, or null"
        assert miss["expected"] is None or miss["expected"] in CASES


@pytest.mark.parametrize("skill", sorted(CASES))
def test_a_prompt_is_never_both_a_positive_and_a_near_miss(skill):
    case = CASES[skill]
    overlap = {p.lower() for p in case["should_trigger"]} & {
        m["prompt"].lower() for m in case["near_miss"]
    }
    assert overlap == set(), f"contradictory expectations: {sorted(overlap)}"


@pytest.mark.parametrize("skill", sorted(CASES))
def test_prompts_are_unique_within_a_skill(skill):
    for group in (CASES[skill]["should_trigger"],
                  [m["prompt"] for m in CASES[skill]["near_miss"]]):
        assert len(group) == len({p.lower() for p in group})


def test_a_near_miss_redirected_elsewhere_is_a_positive_there():
    """If incipit's description must reject a prompt in favour of incipit-review,
    then incipit-review had better claim it — otherwise the prompt matches nothing
    and the redirect is a lie."""
    for skill, case in CASES.items():
        for miss in case["near_miss"]:
            target = miss["expected"]
            if target is None:
                continue
            claimed = {p.lower() for p in CASES[target]["should_trigger"]}
            assert miss["prompt"].lower() in claimed, (
                f"{skill} redirects {miss['prompt']!r} to {target}, "
                f"which does not list it as a should_trigger prompt"
            )


@pytest.mark.parametrize("skill", sorted(CASES))
def test_the_description_names_when_not_to_use_the_skill(skill):
    """Descriptions are the only thing matched at trigger time, so the boundary
    between sibling skills has to live there and not just in the body."""
    text = (SKILLS / "src" / skill / "SKILL.md").read_text(encoding="utf-8")
    description = next(l for l in text.splitlines() if l.startswith("description:"))
    assert "Do not use" in description
