---
name: incipit
description: Research what already exists, then turn a rough idea into a written Implementation Brief and a dependency-ordered task list, saved as files and checked by a verification script. Use when the user has a half-formed idea — software or otherwise — and says "spec this out", "write an implementation brief", "turn this into a mega-prompt", "research this and plan it", "check whether this already exists and then spec it", or names incipit. Do not use when a spec already exists and needs critique (use incipit-review), when only the open questions are wanted (use incipit-clarify), or for a small well-defined change that needs no spec.
version: 1.0.0
author: Incipit
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spec, prompt-engineering, requirements, planning, bmad]
    related_skills: [incipit, incipit-clarify, incipit-review]
---
<!-- Generated from skills/src/incipit by skills/build.py. Do not edit; edit the source and re-run the build. -->

# Incipit — implementation brief wizard

*"here begins."* Incipit turns a rough, half-formed idea into a written
**Implementation Brief** and a task list an agent can execute. You run the flow
yourself in the conversation — there is no server and no separate model.

The value is compression: the quality of an agent's prompt shouldn't depend on the
user remembering to ask themselves every question. Interrogate the idea for them,
draft the spec, write it to disk, and verify it mechanically before handing it over.

## Overview

**Input:** a rough idea, optionally plus a repo path or URL.
**Output:** `brief.md` on disk, plus `research.md` and `tasks.md` above hobby stakes.
**Flow:** frame → calibrate → research → clarify → draft → write → tasks → verify.

## The five rules

These five apply the whole way through. Everything else is stated at the step
where it applies.

1. **The idea goes in verbatim.** Preserve the user's exact phrasing; never
   improve it.
2. **Requirements use the SHALL templates, and every acceptance criterion names
   the requirement IDs it covers.** See
   [reference/requirements-syntax.md](reference/requirements-syntax.md).
3. **Every unstated choice is marked `[ASSUMPTION]`.** Choose the simplest
   mainstream option and label it.
4. **Every externally-owned fact carries a source.** Versions, quotas, rate limits,
   prices, licences, regulations. These are the claims that go stale, and a
   downstream agent will act on them as though they were checked.
5. **Nothing ships until the checker passes.** The verify step is not optional.

## When to use

Use this skill when the user has a rough idea — a piece of software, but equally a
process, a policy, a campaign, or a research plan — and wants a rigorous,
executable specification before work starts. Trigger phrases: "spec this out",
"turn this into a brief", "write an implementation brief", "mega-prompt",
"incipit".

**Don't use it for:** work that is already specced and just needs doing; quick
questions where a full brief is overkill. If the user only wants the clarifying
questions, use `incipit-clarify`. If they already have a spec and want it
critiqued, use `incipit-review`.

## The flow

Keep it tight and fast. Default to smart assumptions and never force a blank the
user doesn't care about.

### 1. Brain dump

Get the idea in the user's own words. Ask only whether this is **new** work or an
**existing** codebase or system.

### 2. Frame it

Pick a short kebab-case `<slug>` for the idea and create `docs/specs/<slug>/`.
Everything from here writes into that directory. If there is no writable working
directory, say so now and present each artifact inline instead.

Then choose the schema. It decides which sections the brief has. Read it now — it
is the spec for every section you will draft.

| The deliverable is | Schema |
|---|---|
| software: an app, service, CLI, library | [reference/schema-software.md](reference/schema-software.md) |
| anything else: a process, policy, campaign, event, research plan | [reference/schema-generic.md](reference/schema-generic.md) |

When it is genuinely mixed, pick software — its sections are stricter and the
extra rigor is harmless. State which schema you chose in one line.

### 3. Calibrate

Infer three values from the idea, **state them in one line**, and invite a
correction. This is inference, not a questionnaire. It comes before the work so the
rest of the flow knows how much rigor to spend.

| Value | Options |
|---|---|
| stakes | `hobby`, `internal`, `serious` |
| form factor | `web app`, `CLI tool`, `API/service`, `mobile app`, `library`, or the non-software equivalent |
| project type | `new`, `existing` |

Stakes sets the rigor, the question count, and which artifacts you produce:

| stakes | context string to reuse in every section | questions | research | tasks |
|---|---|---|---|---|
| `hobby` | personal/hobby project — keep it lean, minimal rigor | 5 | inline | inline |
| `internal` | internal tool — moderate rigor, a few users depend on it | 6 | `research.md` | `tasks.md` |
| `serious` | serious/production project — full rigor, real users and stakes | 8 | `research.md` | `tasks.md` |

**`inline` means the work still happens, in less ceremony.** At `hobby` stakes you
still search, but the findings go into the brief's background and constraints with
a bare URL rather than into a separate file with IDs; and the task list becomes a
short checklist at the end of the brief rather than `tasks.md`, unless the work is
plainly more than one sitting. Compression is the point of this skill — a weekend
tool should not cost three files and a traceability matrix.

Project-type context strings: `new` → "greenfield — no existing work; free to
choose structure and approach." `existing` → "existing system — must integrate
with current architecture and conventions; prefer additive, non-breaking changes."

Derive the form factor from the idea, never from a menu the user clicked earlier,
so it cannot contradict the spec. When you genuinely cannot infer, default to
`internal` / `web app` / `new`.

### 4. Research

Find out what already exists before specifying anything. Follow
[reference/research.md](reference/research.md), which scales the effort to the
stakes you just set.

Two halves, internal first: what has already been built, tried, or rejected *here*
(the code, the tracker, the git history), then what exists *in the world* (prior
art, the current approach, known pitfalls, external limits). Every finding carries a
source, because a claim you cannot source is a guess.

Do not skip this and draft from memory. Model recall has a cutoff and versions,
pricing, quotas, and regulations all move after it. If you have no web access, say
so and record the internal findings only.

**Stop and go back to the user when the verdict is `adopt` or `extend`** — an
existing tool doing the job changes what to build, and that decision is theirs, not
yours. Do not write a brief for something that need not be built.

Treat existing conventions as binding and prefer additive, non-breaking changes.

### 5. Clarify

Ask the N most decision-changing questions — the ones whose answers would most
change how this gets built. **Start from the open questions research could not
settle** — from `## Open questions` in `research.md`, or from what you noted while
searching. Those have already earned their place. Do not ask anything research
already answered; state the finding instead. Give each question a sensible default
prefixed with `[ASSUMPTION]`, in exactly this shape:

```
1. <question>
[ASSUMPTION] <default answer>
2. <question>
[ASSUMPTION] <default answer>
```

The user answers only what they care about. **Every blank falls back to its
`[ASSUMPTION]`.** Record each answer, or the assumption that stood in for it.

### 6. Draft, one section per pass

Draft the schema's sections in the order the schema lists. **Handle one section at
a time**: re-read that section's entry in the schema, draft only that section
against only its rules, then move on. Do not hold all the sections' rules in mind
at once, and do not draft ahead.

Two passes look outside the section:

- **The technology or resources section** is where research lands. Take versions,
  limits, and ruled-out options from what you found and carry the source across —
  finding IDs when there is a `research.md`, a bare URL otherwise. If you find
  yourself about to state a version or a quota that no finding covers, that is a
  missing search, not a detail to guess.
- **The acceptance criteria section** reads back the requirements you already
  wrote and cites their IDs. This is the one place cross-referencing is required.

Output each section as a body under its `## <title>` heading, with no preamble.
Afterward, offer the refine menu in [reference/refine.md](reference/refine.md),
but don't block on it — most sections are fine as drafted.

### 7. Write the files

Assemble the brief **deterministically**: concatenate the header below and the
section bodies exactly as drafted. Do not regenerate or reword anything here.

Write it to `docs/specs/<slug>/brief.md`.

```
# Implementation Brief

You are implementing the following project. Treat every requirement and constraint below as binding. Ask before deviating from the stated constraints; do not add anything listed under Out of Scope.

**Project idea (verbatim from the author):** <idea>
**Project type:** <new|existing> — <project-type context string>
**Stakes:** <hobby|internal|serious> — <stakes context string>
**Form factor:** <form factor>

<the schema's sections, each under its own `## <title>` heading, in schema order>
```

Add these header lines when they apply, directly under **Form factor:**

```
**Existing repository:** <url or path> — integrate with the current codebase; prefer additive, non-breaking changes.
**Research:** research.md
```

The repository line applies when the project type is `existing` **and** the user gave
a repo. The research line applies whenever you wrote a `research.md`.

Tell the user the path you wrote to.

### 8. Break it into tasks

A brief alone still leaves the next agent to plan, and asking for a whole brief in
one shot is the most common way implementation goes wrong. Write a
dependency-ordered task list following [reference/tasks.md](reference/tasks.md) —
to `docs/specs/<slug>/tasks.md`, or as a short checklist at the end of the brief if
the ladder in step 3 put tasks inline.

### 9. Verify

Run the checker and fix what it reports. Pass whichever artifacts exist:

```bash
# hobby: the brief carries everything
python3 scripts/brief_check.py docs/specs/<slug>/brief.md

# internal and above
python3 scripts/brief_check.py docs/specs/<slug>/brief.md \
  --tasks docs/specs/<slug>/tasks.md --research docs/specs/<slug>/research.md
```

At `serious` stakes add `--verify-sources`, which fetches every cited URL and fails
on the dead ones. It needs network access and takes a few seconds, which is why it
is opt-in rather than always on.

It verifies structure, requirement syntax, ID references, citation format, and task
coverage mechanically — things you cannot reliably confirm by rereading your own
output.
Re-run until it exits clean. Report anything it flags that you deliberately chose
to leave, with the reason.

The checker cannot judge content. Confirm these yourself, one at a time:

- [ ] The idea appears verbatim, in the user's own words.
- [ ] Requirements say what the system does, not how it is built.
- [ ] For existing work, the constraints match what the repo actually uses.
- [ ] Out of Scope names the things an agent would otherwise over-build.

### 10. Hand off

Report the paths you wrote and stop. If the user wants the work tracked in an issue
tracker and you have a Jira, Linear, or equivalent tool available, offer it:
one epic from the brief's goals, one issue per task, each carrying its requirement
IDs and a link back to the brief. Confirm before creating anything — these are
writes to a system outside the repo — and never invent a project key.

## Shoot the moon

When the user wants it hands-off ("just do it", "shoot the moon", "run it all"),
skip the interactive Q&A: infer the calibration, generate the clarifying questions
but **take every `[ASSUMPTION]` as the answer**, then run the remaining steps
normally. Hands-off means no questions — not no research, no files, and no checker.
The one thing it does not override is a verdict of `adopt`: if research finds
something that already does the job, say so and stop, because building anyway is
not what "just do it" meant.

## Common pitfalls

- **Asking what you could infer.** Stakes and form factor are inferred and stated,
  never asked as a questionnaire.
- **Questions without defaults.** A question with no `[ASSUMPTION]` forces the user
  to think about something they may not care about.
- **Drafting all sections in one pass.** Rules bleed together and the ones about
  cross-referencing are the first to get dropped. One section, one pass.
- **Rewriting at assembly.** Assembly is concatenation. Regenerating there silently
  discards the user's edits and approved refinements.
- **Greenfield answers for existing work.** If you skipped the research step, the
  constraints will contradict the repo.
- **Full ceremony on a small idea.** Three files and a traceability matrix for a
  weekend script is the opposite of compression. Let the ladder in step 3 decide.
- **Specifying from recall.** A version, quota, price, or limit stated without a
  finding behind it is a guess, and the ones that go stale fastest are exactly the
  ones a coding agent will trust.
- **Researching and then ignoring it.** A finding nothing in the brief cites either
  should have changed the brief or shouldn't have been recorded.
- **Asking what research already answered.** The clarifying questions come from
  `research.md`'s open questions, not from a fresh blank page.
- **Treating the checker as advisory.** A brief that fails the checker is not
  finished, however good it reads.
- **Gold-plating.** Out of Scope exists to stop the downstream agent from building
  auth, admin UIs, and scaling work nobody asked for.
