---
name: incipit-clarify
description: Interrogate an idea with the handful of decision-changing questions that actually matter, each carrying a sensible default assumption. Use when the user wants an idea stress-tested or the open questions surfaced, and asks "what am I missing" or "what should I decide first". Do not use when they want the finished specification document (use incipit) or want an existing spec critiqued (use incipit-review).
version: 1.0.0
author: Incipit
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spec, prompt-engineering, requirements, planning, bmad]
    related_skills: [incipit, incipit-clarify, incipit-review]
---
<!-- Generated from skills/src/incipit-clarify by skills/build.py. Do not edit; edit the source and re-run the build. -->

# Incipit clarify — the questions that matter

Surface the small set of questions whose answers would most change how something
gets built, and give each one a default so the user only has to engage with what
they care about. This is the elicitation half of `incipit` on its own, for when a
full Implementation Brief is more than the user wants.

It applies to anything that has to be planned before it is done — a piece of
software, but equally a process, a policy, a campaign, or a research plan.

## When to use

Use this skill when the user:

- has an idea and wants to know what they haven't thought about;
- asks "what am I missing", "what should I decide first", or "what do you need to
  know to build this";
- is about to write a spec or ticket themselves and wants the open questions.

If they want the finished specification, use `incipit` instead. If they already
have a spec and want it critiqued, use `incipit-review`.

## Flow

### 1. Take the idea as given

Don't rewrite or improve the idea. Work from the user's own words.

### 2. Calibrate silently, then state it in one line

Infer the stakes, form factor, and whether this is new or existing work. State the
inference in a single line and invite a correction rather than asking a series of
setup questions.

| stakes | rigor | questions |
|---|---|---|
| `hobby` | lean, minimal rigor | 5 |
| `internal` | moderate rigor, a few users depend on it | 6 |
| `serious` | full rigor, real users and stakes | 8 |

### 3. Check what already exists

A question research can answer is a question not worth asking. Before drafting the
list, spend a little effort finding out:

- **In the repo or the tracker.** Half-built versions and previously rejected
  proposals are common, and a closed ticket explaining why something was dropped is
  worth more than any question you could ask. `incipit` ships
  `scripts/repo_context.py` for a fast codebase summary.
- **On the web, if the idea might already be solved.** One or two searches. If a
  tool already does this, tell the user that instead of interrogating them about
  building it — that is the single most useful answer you can give here.

Anything you settle this way becomes context you state, not a question you ask.
Anything you can't settle is a candidate for the list below.

### 4. Ask

Output exactly this shape, nothing else:

```
1. <question>
[ASSUMPTION] <default answer>
2. <question>
[ASSUMPTION] <default answer>
```

## What makes a question worth asking

A question earns its place only if different answers lead to genuinely different
implementations. Prioritize by that test:

- **Scope boundaries** — what's explicitly not in the first version.
- **Data and state** — what is stored, where, and who owns it.
- **Integration points** — what existing systems this must not break.
- **Users and access** — who uses it and whether auth is real or absent.
- **Deployment target** — where it runs, since it constrains the whole stack.
- **The single riskiest unknown** — whatever would most hurt if guessed wrong.

Skip questions whose answer you can already infer, questions about preferences
that don't change the build, anything the user already answered in their brain
dump, and anything step 3 settled — state that as a finding instead.

## Assumption quality

The default is the point of the exercise. A weak default forces the user to think;
a strong one lets them skip the question entirely.

- Pick the simplest mainstream option, not the most capable one.
- Match the stated stakes — don't propose Kubernetes for a hobby project.
- For existing codebases, default to whatever the repo already does.
- Where step 3 turned something up, default to it and say where it came from. A
  default backed by a source is one the user can accept without thinking.
- Make it a real, committable answer, never "TBD" or "depends".

## After the questions

Note that blanks fall back to their assumption, and offer the obvious next step:
turning the answers into a full Implementation Brief with `incipit`.
