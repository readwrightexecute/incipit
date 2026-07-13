---
name: incipit
description: "Incipit: turn a rough software idea into a single structured Implementation Brief (mega-prompt) through a compressed calibrate → clarify → draft-six-sections flow. Use when the user has a half-formed software idea and wants a rigorous, paste-ready spec before building."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spec, prompt-engineering, requirements, bmad, planning]
    related_skills: []
---

# Incipit — mega-prompt wizard

*"here begins."* Incipit turns a rough, half-formed software idea into a single
structured **Implementation Brief** (a "mega-prompt") ready to paste into — or hand
straight to — a coding agent. This skill makes **you, the host agent, run the flow
yourself** in the conversation. There is no web app and no separate model endpoint:
you act as the wizard's model.

The value is compression: the quality of a coding-agent prompt shouldn't depend on
the user remembering to ask themselves every question. You interrogate the idea for
them, draft the spec, and converge it — so they can paste the result into an agent
and have it succeed on the first try, without a back-and-forth.

## Overview

Input: a rough software idea (plus, optionally, a repo for existing projects).
Output: one Markdown **Implementation Brief** with six sections, assembled
deterministically. The flow is `calibrate → clarify → draft six sections → assemble`,
with an optional per-section refine menu and a hands-off one-shot mode.

## When to use this skill

Use it when the user:
- has a rough or half-formed **software** idea and wants a rigorous, paste-ready spec;
- says things like "spec this out", "turn this idea into a prompt/brief", "write an
  implementation brief", "mega-prompt", or invokes "incipit";
- wants to plan *what* to build before an agent starts building it.

**Don't use for:** already-specced work that just needs coding; non-software
requests; or quick one-line answers where a full brief is overkill.

## The flow (interactive — default)

Run these steps in order, in the chat. Keep it tight and fast; respect the user's
time (default smart assumptions, never force a blank they don't care about).

### 1. Brain dump
Get the idea in the user's own words. Keep their exact phrasing — it goes into the
final brief verbatim. Ask only whether it's a **new** project or an **existing**
codebase. If existing and they give a repo link/path, skim the README + structure
first so your questions and sections fit the *real* codebase (prefer additive,
non-breaking changes), not a greenfield one.

### 2. Calibrate
Infer three things from the idea, **state them to the user in one line**, and invite
a correction (this is inference, not a questionnaire):

- **stakes** — one of `hobby` | `internal` | `serious`
- **form factor** — one of `web app` | `CLI tool` | `API/service` | `mobile app`
  (inferred from the idea, *not* asked — a stale menu choice must never contradict
  the spec)
- **project type** — `new` | `existing`

These drive the rest of the flow:

| stakes | meaning (use as context in every section) | # clarifying questions |
|---|---|---|
| `hobby` | personal/hobby project — keep it lean, minimal rigor | 5 |
| `internal` | internal tool — moderate rigor, a few users depend on it | 6 |
| `serious` | serious/production project — full rigor, real users and stakes | 8 |

Project-type context: `new` → "greenfield — no existing code; free to choose
structure and stack." `existing` → "existing codebase — must integrate with current
architecture and conventions; prefer additive, non-breaking changes."

If you can't infer a value, default to `internal` / `web app` / `new`.

### 3. Clarify
Ask the **N most decision-changing questions** (N from the table above). For each,
provide a sensible default prefixed with `[ASSUMPTION]`. Present them exactly:

```
1. <question>
[ASSUMPTION] <default answer>
2. <question>
[ASSUMPTION] <default answer>
...
```

The user answers only what they care about; **any blank falls back to its
`[ASSUMPTION]`**. Record each answer (or the assumption) — thread them into every
section.

### 4. Draft the six sections
Draft the six sections below **sequentially, in the given order**. This order is
load-bearing: when drafting each section, keep the **already-drafted sections in
context** and stay consistent with them (don't repeat their content; e.g. Acceptance
Criteria must map to the Functional Requirements you already wrote). Thread in the
clarifications (question → answer, using the `[ASSUMPTION]` where the user was
silent). Output each section as a body under its `## <title>` heading — no preamble.
See **Section definitions** below.

### 5. Assemble
Assemble the final brief **deterministically** — do not re-generate or rewrite the
sections at this step. Concatenate the header + the six section bodies exactly as
specified under **Final assembly format**.

## Shoot the Moon (one-shot mode)

If the user wants it hands-off ("just do it", "shoot the moon", "run it all"), skip
the interactive Q&A: infer the calibration, generate the clarifying questions but
**take every `[ASSUMPTION]` as the answer**, draft all six sections, and output the
finished brief in one pass. Tell the user they can still refine any section
afterward.

## Section definitions

Draft these in order. Each `instruction` is the spec for that section's body.

1. **Goals & Background** — Write a short "Goals & Background" section: 3-6 bullet
   points capturing the desired outcomes, followed by one short paragraph of
   background context explaining why this is being built. Capability language only —
   no implementation details.

2. **Functional Requirements** — Write the functional requirements as a numbered
   list FR1, FR2, ... Each requirement must be a single testable statement of WHAT
   the system does (e.g. "FR3: Users can export the result as a markdown file").
   Cover the core happy path first, then secondary behaviors. 5-12 requirements
   depending on stakes. Do not include performance/quality attributes here.

3. **Non-Functional Requirements** — Write the non-functional requirements as a
   numbered list NFR1, NFR2, ... covering only the attributes that matter for these
   stakes: performance, security/auth, reliability, resource constraints,
   compatibility. Keep it to 3-7 items. Each must be concrete and checkable (e.g.
   "NFR2: First page load under 2s on LAN"), not aspirational fluff.

4. **Tech Constraints & Stack** — Write a "Tech Constraints & Stack" section: a
   definitive bullet list of the technology choices and constraints a coding agent
   must respect — language/runtime, frameworks, storage, deployment target, existing
   systems to integrate with, and anything explicitly ruled out. Derive choices from
   the user's answers; where the user expressed no preference, choose the simplest
   mainstream option and mark it "[ASSUMPTION]".

5. **Acceptance Criteria** — Write the acceptance criteria as a numbered list. Each
   criterion is a concrete, observable check in Given/When/Then form or "Done when
   ..." form, mapped to the functional requirements. Include at least one criterion
   for error/edge behavior. 5-10 criteria.

6. **Out of Scope** — Write a short "Out of Scope" section: 3-6 bullets explicitly
   excluding things a coding agent might otherwise gold-plate (extra platforms, auth
   systems, scaling work, admin UIs, etc.) based on the stated stakes and idea. One
   line each, no explanations.

## Refine methods (optional, per section)

Offer these after a section is drafted; apply whichever the user picks. Each rewrites
the **whole** section and returns only the revised body in the same format — preserve
every existing item, label, and identifier (FR1, NFR2, ...) the method doesn't
explicitly change.

- **Critique & Refine** — Act as a harsh reviewer of the section. Identify
  weaknesses, vagueness, and missed implications, then rewrite the section fixing
  them.
- **Identify Risks** — Identify the biggest risks and unstated assumptions lurking
  in the section, then rewrite it so those risks are addressed or made explicit (as
  constraints, requirements, or "[RISK]" notes).
- **Expand** — The section is too thin. Expand it with the next most valuable
  items/details implied by the project context but missing. Keep the same format and
  numbering; don't pad with fluff.
- **Simplify** — The section is overbuilt for the stated stakes. Cut it to the
  essential minimum a coding agent needs — merge overlapping items, drop
  gold-plating, tighten wording. Keep the same format and numbering.

## Writing rules

Adopt this persona for all generation: **a senior product manager turning a rough
idea into a precise, structured specification.** Write tight, concrete, testable
specs — never marketing fluff. Follow each output-format instruction exactly: no
preamble, no closing remarks, no code fences wrapping a whole section. Prefer the
simplest mainstream option where the user has no preference, and mark such choices
`[ASSUMPTION]`.

## Final assembly format

Emit the final brief as one Markdown document with this exact shape (the section
titles are the six above, in order):

```
# Implementation Brief

You are implementing the following project. Treat every requirement and constraint below as binding. Ask before deviating from the Tech Constraints; do not add anything listed under Out of Scope.

**Project idea (verbatim from the author):** <idea>
**Project type:** <new|existing> — <project-type context string>
**Stakes:** <hobby|internal|serious> — <stakes context string>
**Form factor:** <form factor>

## Goals & Background
<section body>

## Functional Requirements
<section body>

## Non-Functional Requirements
<section body>

## Tech Constraints & Stack
<section body>

## Acceptance Criteria
<section body>

## Out of Scope
<section body>
```

Only when project type is `existing` **and** the user gave a repo, add this line
directly under **Form factor:**

```
**Existing repository:** <url> — integrate with the current codebase; prefer additive, non-breaking changes.
```

Present the assembled brief in a single code block so the user can copy it whole.

## Common Pitfalls

- **Asking the form factor instead of inferring it.** Infer it from the idea and just
  state it; asking invites a stale answer that contradicts the spec.
- **Over-questioning.** Ask only the N decision-changing questions, each with an
  `[ASSUMPTION]`. Don't turn calibration into an interrogation.
- **Drafting sections in isolation.** Later sections must see earlier ones —
  Acceptance Criteria maps to the Functional Requirements you already wrote.
- **Regenerating at assembly.** Assembly is pure concatenation of the header + the
  six drafted bodies. Don't rewrite content in this step.
- **Dropping content during a refine.** Refine rewrites the *whole* section and keeps
  every identifier and item the method didn't explicitly change.
- **Gold-plating for the stakes.** A `hobby` idea gets a lean spec; reserve full
  rigor for `serious`.

## Verification Checklist

- [ ] Stakes, form factor, and project type were stated and confirmed (or defaulted).
- [ ] Clarifying question count matched stakes (hobby 5 / internal 6 / serious 8),
      each with an `[ASSUMPTION]` default; blanks fell back to the assumption.
- [ ] All six sections present, in order, each under its `## <title>` heading.
- [ ] Functional Requirements numbered FR1..; Non-Functional numbered NFR1..;
      Acceptance Criteria map to the FRs and include an error/edge case.
- [ ] Assumed technology choices are marked `[ASSUMPTION]`.
- [ ] Final brief starts with the exact `# Implementation Brief` header + metadata
      lines; `**Existing repository:**` line present iff existing + repo given.
- [ ] Brief delivered in one copyable code block.
