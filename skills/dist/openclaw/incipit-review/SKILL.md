---
name: incipit-review
description: Review an existing spec, PRD, ticket, or implementation brief for gaps, untestable requirements, hidden risks, and scope creep before an agent acts on it. Use when the user has a written spec — for software or for any other planned work — and asks whether it is ready to build, or wants it critiqued, audited, or tightened. Do not use when there is no document yet (use incipit to write one, or incipit-clarify for the open questions).
---
<!-- Generated from skills/src/incipit-review by skills/build.py. Do not edit; edit the source and re-run the build. -->

# Incipit review — audit a spec before it ships

A spec fails a coding agent in predictable ways: requirements that can't be
checked, decisions left implicit, scope that quietly doubles, and no statement of
what *not* to build. Find those, rank them, and hand back fixes.

## When to use

Use this skill when the user:

- has a spec, PRD, ticket, design doc, or Implementation Brief and asks if it's
  ready to build;
- says "review this spec", "critique this", "what's missing", or "audit this brief";
- is about to hand a document to a coding agent and wants it de-risked first.

If there's no document yet, use `incipit` to produce one or `incipit-clarify` to
surface the open questions.

## Flow

### 1. Read the spec and the ground truth

Read the document in full. Then check its claims against reality rather than
against your own recall, which has the same cutoff the author's did:

- **The codebase.** If the spec targets existing code, read enough of it to know
  whether the spec's claims hold — a spec that contradicts the repo is the most
  expensive kind of wrong. `incipit` ships `scripts/repo_context.py` for a fast
  summary.
- **The web, for anything versioned or externally owned.** Every named library
  version, API limit, quota, price, licence, and regulation is a factual claim with
  an expiry date. Spot-check the load-bearing ones. A confidently stated stale
  version is worse than an unstated one, because an agent will act on it.
- **Prior art, if the spec never mentions any.** A brief that proposes building
  something a standard tool already does is a High finding no matter how well it is
  written, and it is the one an author almost never catches themselves.

### 2. Run the checker first, if it applies

When the document is an Implementation Brief written by `incipit` — it opens with
`# Implementation Brief` — get the mechanical findings for free before spending
judgment on them:

```bash
python3 scripts/brief_check.py <path to brief.md> \
  [--tasks <path to tasks.md>] [--research <path to research.md>]
```

Everything it reports is a real finding. Fold its output into your report rather
than repeating the same checks by eye, and spend your own attention on what a
script cannot judge: whether the requirements describe the right system.

### 3. Audit against the rubric

Check the spec for each of the six concerns below. A concern can be satisfied
anywhere in the document; don't require matching headings, and don't require
software-specific ones when the work isn't software.

| Concern | Passes when |
|---|---|
| Goals & background | The outcome and the reason for doing it are both stated |
| Prior art | Existing solutions were considered, and building anyway is justified |
| Requirements | Each is a single testable statement of what happens, ideally in `SHALL` form |
| Quality attributes | Concrete and measurable, not "fast" or "secure" |
| Constraints | Stack, resources, and target are decided, not deferred |
| Acceptance criteria | Observable, mapped to requirements, including error and edge behavior |
| Out of scope | Names what an agent would otherwise over-build |

### 4. Report findings

Group findings by severity and lead with the ones that would derail
implementation. For each: what's wrong, why it matters, and the concrete fix.

```
## Findings

### High — blocks implementation
- **<finding>** — <why it matters>. Fix: <specific change>.

### Medium — will cause rework
- **<finding>** — <why it matters>. Fix: <specific change>.

### Low — worth tightening
- **<finding>** — <why it matters>. Fix: <specific change>.

## Verdict
<ready to build | ready after the High items | needs rework>, in one or two sentences.
```

Severity is about consequence, not confidence. High means an agent would build the
wrong thing or get blocked. Medium means avoidable rework. Low is polish.

### 5. Offer the rewrite

Offer to apply the fixes. If the user accepts, rewrite the affected sections in
place, preserving their structure, numbering, and wording wherever the fix doesn't
require a change. Don't rewrite the whole document when three sections are at
fault.

When rewriting a requirement that isn't checkable, put it in one of the `SHALL`
templates in `incipit`'s `reference/requirements-syntax.md`. That converts a
judgment about testability into a form the checker can confirm. If you rewrote a
brief that the checker covers, re-run it before handing back.

## What to look for

- **Untestable requirements.** Adjectives without numbers. "Responsive",
  "intuitive", "scalable" are not requirements.
- **Implicit decisions.** A stack, storage engine, or auth model assumed but never
  stated, so the agent picks its own.
- **Orphaned criteria.** Acceptance criteria that map to no requirement, or
  requirements no criterion checks.
- **Missing error paths.** Only happy-path behavior specified.
- **Silent scope creep.** Requirements that smuggle in a second feature.
- **No exclusions.** With nothing out of scope, an agent adds auth, an admin UI,
  and a caching layer nobody asked for.
- **Contradicting the codebase.** Constraints that name tools the repo doesn't use.
- **Stale references.** A named library, version, vendor, or regulation that no
  longer exists or has been superseded. Search rather than trusting recall.
- **Unsourced specifics.** A precise number — a rate limit, quota, price, timeout —
  with nothing behind it. Precision without a source is the most convincing kind of
  guess, and downstream agents treat it as settled.
- **Reinventing something standard.** Requirements describing work a well-known
  library or service already does, with no reason given for building it here.
- **No ordering.** A spec with no task breakdown leaves an agent to attempt
  everything at once, which is how implementations sprawl.
- **Stakes mismatch.** Production rigor on a weekend project, or the reverse.

## Calibration

Judge the spec against its own stakes rather than a universal bar. A hobby project
doesn't need an SLO, and a payments service does. Over-specification is a real
finding: flag rigor the project can't justify as `Low` or `Medium` rather than
praising it.
