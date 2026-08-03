# Incipit

Instruction-only fallback for hosts that read `AGENTS.md` but do not support invocable skills. It inlines all three Incipit skills; a skill-capable host should install the real skills instead. The helper scripts (`scripts/brief_check.py`, `scripts/repo_context.py`) are not inlined here: fetch them from the incipit repository, or perform the checks they automate by hand.

## Incipit — implementation brief wizard

*"here begins."* Incipit turns a rough, half-formed idea into a written
**Implementation Brief** and a task list an agent can execute. You run the flow
yourself in the conversation — there is no server and no separate model.

The value is compression: the quality of an agent's prompt shouldn't depend on the
user remembering to ask themselves every question. Interrogate the idea for them,
draft the spec, write it to disk, and verify it mechanically before handing it over.

### Overview

**Input:** a rough idea, optionally plus a repo path or URL.
**Output:** `brief.md` on disk, plus `research.md` and `tasks.md` above hobby stakes.
**Flow:** frame → calibrate → research → clarify → draft → write → tasks → verify.

### The five rules

These five apply the whole way through. Everything else is stated at the step
where it applies.

1. **The idea goes in verbatim.** Preserve the user's exact phrasing; never
   improve it.
2. **Requirements use the SHALL templates, and every acceptance criterion names
   the requirement IDs it covers.** See
   [Requirement syntax](#requirement-syntax).
3. **Every unstated choice is marked `[ASSUMPTION]`.** Choose the simplest
   mainstream option and label it.
4. **Every externally-owned fact carries a source.** Versions, quotas, rate limits,
   prices, licences, regulations. These are the claims that go stale, and a
   downstream agent will act on them as though they were checked.
5. **Nothing ships until the checker passes.** The verify step is not optional.

### When to use

Use this skill when the user has a rough idea — a piece of software, but equally a
process, a policy, a campaign, or a research plan — and wants a rigorous,
executable specification before work starts. Trigger phrases: "spec this out",
"turn this into a brief", "write an implementation brief", "mega-prompt",
"incipit".

**Don't use it for:** work that is already specced and just needs doing; quick
questions where a full brief is overkill. If the user only wants the clarifying
questions, use `incipit-clarify`. If they already have a spec and want it
critiqued, use `incipit-review`.

### The flow

Keep it tight and fast. Default to smart assumptions and never force a blank the
user doesn't care about.

#### 1. Brain dump

Get the idea in the user's own words. Ask only whether this is **new** work or an
**existing** codebase or system.

#### 2. Frame it

Pick a short kebab-case `<slug>` for the idea and create `docs/specs/<slug>/`.
Everything from here writes into that directory. If there is no writable working
directory, say so now and present each artifact inline instead.

Then choose the schema. It decides which sections the brief has. Read it now — it
is the spec for every section you will draft.

| The deliverable is | Schema |
|---|---|
| software: an app, service, CLI, library | [Software schema](#software-schema) |
| anything else: a process, policy, campaign, event, research plan | [Generic schema](#generic-schema) |

When it is genuinely mixed, pick software — its sections are stricter and the
extra rigor is harmless. State which schema you chose in one line.

#### 3. Calibrate

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

#### 4. Research

Find out what already exists before specifying anything. Follow
[Research protocol](#research-protocol), which scales the effort to the
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

#### 5. Clarify

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

#### 6. Draft, one section per pass

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
Afterward, offer the refine menu in [Refine methods](#refine-methods),
but don't block on it — most sections are fine as drafted.

#### 7. Write the files

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

#### 8. Break it into tasks

A brief alone still leaves the next agent to plan, and asking for a whole brief in
one shot is the most common way implementation goes wrong. Write a
dependency-ordered task list following [Task breakdown](#task-breakdown) —
to `docs/specs/<slug>/tasks.md`, or as a short checklist at the end of the brief if
the ladder in step 3 put tasks inline.

#### 9. Verify

Run the checker and fix what it reports. Pass whichever artifacts exist:

```bash
# hobby: the brief carries everything
python3 scripts/brief_check.py docs/specs/<slug>/brief.md

# internal and above
python3 scripts/brief_check.py docs/specs/<slug>/brief.md \
  --tasks docs/specs/<slug>/tasks.md --research docs/specs/<slug>/research.md
```

`scripts/brief_check.py` resolves against this skill's directory; the
`docs/specs/` paths resolve against the project root. Qualify whichever side
your working directory doesn't cover.

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

#### 10. Hand off

Report the paths you wrote and stop. If the user wants the work tracked in an issue
tracker and you have a Jira, Linear, or equivalent tool available, offer it:
one epic from the brief's goals, one issue per task, each carrying its requirement
IDs and a link back to the brief. Confirm before creating anything — these are
writes to a system outside the repo — and never invent a project key.

### Shoot the moon

When the user wants it hands-off ("just do it", "shoot the moon", "run it all"),
skip the interactive Q&A: infer the calibration, generate the clarifying questions
but **take every `[ASSUMPTION]` as the answer**, then run the remaining steps
normally. Hands-off means no questions — not no research, no files, and no checker.
The one thing it does not override is a verdict of `adopt`: if research finds
something that already does the job, say so and stop, because building anyway is
not what "just do it" meant.

### Common pitfalls

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

---

## Incipit clarify — the questions that matter

Surface the small set of questions whose answers would most change how something
gets built, and give each one a default so the user only has to engage with what
they care about. This is the elicitation half of `incipit` on its own, for when a
full Implementation Brief is more than the user wants.

It applies to anything that has to be planned before it is done — a piece of
software, but equally a process, a policy, a campaign, or a research plan.

### When to use

Use this skill when the user:

- has an idea and wants to know what they haven't thought about;
- asks "what am I missing", "what should I decide first", or "what do you need to
  know to build this";
- is about to write a spec or ticket themselves and wants the open questions.

If they want the finished specification, use `incipit` instead. If they already
have a spec and want it critiqued, use `incipit-review`.

### Flow

#### 1. Take the idea as given

Don't rewrite or improve the idea. Work from the user's own words.

#### 2. Calibrate silently, then state it in one line

Infer the stakes, form factor, and whether this is new or existing work. State the
inference in a single line and invite a correction rather than asking a series of
setup questions.

| stakes | rigor | questions |
|---|---|---|
| `hobby` | lean, minimal rigor | 5 |
| `internal` | moderate rigor, a few users depend on it | 6 |
| `serious` | full rigor, real users and stakes | 8 |

#### 3. Check what already exists

A question research can answer is a question not worth asking. Before drafting the
list, spend a little effort finding out:

- **In the repo or the tracker.** Half-built versions and previously rejected
  proposals are common, and a closed ticket explaining why something was dropped is
  worth more than any question you could ask. This skill bundles
  `scripts/repo_context.py` (in this skill's directory) for a fast codebase summary.
- **On the web, if the idea might already be solved.** One or two searches. If a
  tool already does this, tell the user that instead of interrogating them about
  building it — that is the single most useful answer you can give here.

Anything you settle this way becomes context you state, not a question you ask.
Anything you can't settle is a candidate for the list below.

#### 4. Ask

Output exactly this shape, nothing else:

```
1. <question>
[ASSUMPTION] <default answer>
2. <question>
[ASSUMPTION] <default answer>
```

### What makes a question worth asking

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

### Assumption quality

The default is the point of the exercise. A weak default forces the user to think;
a strong one lets them skip the question entirely.

- Pick the simplest mainstream option, not the most capable one.
- Match the stated stakes — don't propose Kubernetes for a hobby project.
- For existing codebases, default to whatever the repo already does.
- Where step 3 turned something up, default to it and say where it came from. A
  default backed by a source is one the user can accept without thinking.
- Make it a real, committable answer, never "TBD" or "depends".

### After the questions

Note that blanks fall back to their assumption, and offer the obvious next step:
turning the answers into a full Implementation Brief with `incipit`.

---

## Incipit review — audit a spec before it ships

A spec fails a coding agent in predictable ways: requirements that can't be
checked, decisions left implicit, scope that quietly doubles, and no statement of
what *not* to build. Find those, rank them, and hand back fixes.

### When to use

Use this skill when the user:

- has a spec, PRD, ticket, design doc, or Implementation Brief and asks if it's
  ready to build;
- says "review this spec", "critique this", "what's missing", or "audit this brief";
- is about to hand a document to a coding agent and wants it de-risked first.

If there's no document yet, use `incipit` to produce one or `incipit-clarify` to
surface the open questions.

### Flow

#### 1. Read the spec and the ground truth

Read the document in full. Then check its claims against reality rather than
against your own recall, which has the same cutoff the author's did:

- **The codebase.** If the spec targets existing code, read enough of it to know
  whether the spec's claims hold — a spec that contradicts the repo is the most
  expensive kind of wrong. This skill bundles `scripts/repo_context.py` (in this
  skill's directory) for a fast summary.
- **The web, for anything versioned or externally owned.** Every named library
  version, API limit, quota, price, licence, and regulation is a factual claim with
  an expiry date. Spot-check the load-bearing ones. A confidently stated stale
  version is worse than an unstated one, because an agent will act on it.
- **Prior art, if the spec never mentions any.** A brief that proposes building
  something a standard tool already does is a High finding no matter how well it is
  written, and it is the one an author almost never catches themselves.

#### 2. Run the checker first, if it applies

When the document is an Implementation Brief written by `incipit` — it opens with
`# Implementation Brief` — get the mechanical findings for free before spending
judgment on them:

```bash
python3 scripts/brief_check.py <path to brief.md> \
  [--tasks <path to tasks.md>] [--research <path to research.md>]
```

`scripts/brief_check.py` is bundled with this skill and resolves against this
skill's directory; the document paths resolve against the project.

Everything it reports is a real finding. Fold its output into your report rather
than repeating the same checks by eye, and spend your own attention on what a
script cannot judge: whether the requirements describe the right system.

#### 3. Audit against the rubric

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

#### 4. Report findings

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

#### 5. Offer the rewrite

Offer to apply the fixes. If the user accepts, rewrite the affected sections in
place, preserving their structure, numbering, and wording wherever the fix doesn't
require a change. Don't rewrite the whole document when three sections are at
fault.

When rewriting a requirement that isn't checkable, put it in one of the `SHALL`
templates in `incipit`'s `reference/requirements-syntax.md`. That converts a
judgment about testability into a form the checker can confirm. If you rewrote a
brief that the checker covers, re-run it before handing back.

### What to look for

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

### Calibration

Judge the spec against its own stakes rather than a universal bar. A hobby project
doesn't need an SLO, and a payments service does. Over-specification is a real
finding: flag rigor the project can't justify as `Low` or `Medium` rather than
praising it.

---

## Refine methods

Offer these after a section is drafted and apply whichever the user picks. Each
method rewrites the **whole** section and returns only the revised body in the same
format. Preserve every existing item, label, and identifier (FR1, NFR2, ...) the
method does not explicitly change, and keep the user's own edits unless the method
is specifically fixing them.

### Critique & Refine

Act as a harsh reviewer of the section. Identify weaknesses, vagueness, and missed
implications, then rewrite the section fixing them.

### Identify Risks

Identify the biggest risks and unstated assumptions lurking in the section, then
rewrite it so those risks are addressed or made explicit — as constraints,
requirements, or `[RISK]` notes.

### Expand

The section is too thin. Expand it with the next most valuable items and details
implied by the project context but missing. Keep the same format and numbering
scheme; do not pad with fluff.

### Simplify

The section is overbuilt for the stated stakes. Cut it to the essential minimum a
coding agent needs — merge overlapping items, drop gold-plating, tighten wording.
Keep the same format and numbering scheme.

### Applying a refinement

Keep the previous version of the section until the user accepts the new one, so a
refinement that makes a section worse can be rolled back. If a refinement fails or
returns something malformed, restore the previous body rather than leaving the
section empty.

---

## Requirement syntax

Every requirement in a brief is written with one of five templates. This is EARS —
the Easy Approach to Requirements Syntax, developed at Rolls-Royce and presented at
IEEE RE09 — and it is not decoration. "Write a testable requirement" is a judgment
call that gets dropped under load; "start the line with WHEN and include SHALL" is
a form you either filled in or didn't, and the checker can tell the difference.

The templates also force you to name things you would otherwise leave implicit: the
trigger, the actor, and the observable result.

### The five templates

Replace `THE SYSTEM` with the actor the requirement binds — `THE SYSTEM`,
`THE SERVICE`, `THE PROCESS`, `THE REVIEWER`. Keep it consistent within a brief.

| Pattern | Template | Use for |
|---|---|---|
| Ubiquitous | `THE SYSTEM SHALL <action>` | behavior that is always true |
| Event-driven | `WHEN <trigger>, THE SYSTEM SHALL <action>` | behavior triggered by something |
| State-driven | `WHILE <state>, THE SYSTEM SHALL <action>` | behavior that holds during a state |
| Optional | `WHERE <feature is present>, THE SYSTEM SHALL <action>` | behavior conditional on a feature |
| Unwanted | `IF <condition>, THEN THE SYSTEM SHALL <action>` | errors and edge cases |

Every requirement line contains the word `SHALL`. That is the one hard rule.

### Examples

Good:

```
FR1: THE SYSTEM SHALL store each brief as a Markdown file under docs/specs/.
FR2: WHEN the user submits an empty idea, THE SYSTEM SHALL reject it and explain why.
FR3: WHILE a draft is unsaved, THE SYSTEM SHALL disable the export button.
FR4: WHERE a repository path is supplied, THE SYSTEM SHALL read its stack before asking questions.
FR5: IF the write to disk fails, THEN THE SYSTEM SHALL present the brief inline instead.
```

Bad, and why:

| Written as | Problem |
|---|---|
| `FR1: The app should be fast.` | no actor, no trigger, not observable |
| `FR2: Handle errors gracefully.` | which errors, and what does the system do |
| `FR3: Users can export results.` | a capability, not a behavior with a trigger |
| `FR4: THE SYSTEM SHALL use PostgreSQL.` | that is a constraint, not a requirement |

### Numbering and references

- Functional requirements are `FR1`, `FR2`, ... — one per line, no gaps, no reuse.
- Non-functional requirements are `NFR1`, `NFR2`, ... on the same terms.
- Every acceptance criterion begins with the IDs it covers in square brackets:
  `AC1: [FR2, FR5] ...`. Every FR must be covered by at least one criterion.

The bracketed prefix exists so coverage is mechanically checkable. Prose like
"this criterion relates to the export requirement" is not.

### Coverage floor

Whatever the stakes, a brief must contain **at least one `IF ... THEN`
requirement**. A spec with only happy-path behavior has not been thought through,
and since every requirement must also be covered by a criterion, one unwanted-
behavior requirement guarantees one error-path check.

This is why the error path is expressed as a template rather than as an
instruction to "consider edge cases": the template is something the checker can
confirm, and an instruction is something it cannot.

---

## Research protocol

Before specifying anything, find out what already exists. The most expensive brief
is a well-written one for something that was already solved, already tried here and
abandoned for a reason, or blocked by a constraint nobody looked up.

This phase answers four questions and writes the answers down with citations, so
the brief rests on recorded evidence instead of model recall. Recall is the problem:
model training data has a cutoff, and library versions, pricing, API limits, and
regulations all move after it.

Research has two halves. Do the internal half first — it is cheaper, and it often
ends the research early.

### Internal: what has already been done here

- **The code.** Run `python3 scripts/repo_context.py <path>` for the stack and
  layout, then search for whatever the idea actually touches. Half-built versions
  of the requested feature are common and rarely mentioned by the requester.
- **The tracker and the docs.** If a Jira, Linear, Confluence, Notion, or
  equivalent tool is available, search it for the feature name and its obvious
  synonyms. Look for prior attempts, rejected proposals, and existing tickets.
  A closed ticket saying "won't do, because X" is the single most valuable thing
  you can find, and it never turns up in a web search.
- **The history.** For work that was tried and reverted, `git log --oneline
  --all --grep=<term>` finds it faster than reading code.

Cite internal findings by where they live: `repo:app/auth.py:40`, `PROJ-412`,
`confluence:Onboarding Redesign`.

### External: what exists in the world

Search the web for these four, in this order. Stop as soon as a finding changes the
plan — if step 1 turns up a tool that does the whole job, take that to the user
before researching how to build it.

1. **Prior art.** Does this already exist, as a product, a library, or a pattern?
   Search the problem in the words a user would use, not the words of your intended
   solution. Then search the relevant registry or marketplace directly — npm, PyPI,
   crates.io, the extension store — because search engines surface blog posts about
   tools more readily than the tools.
2. **The current approach.** What is the accepted way to do this now, and what is
   the current version of whatever you would use? Confirm versions against the
   registry page or the changelog, never a tutorial — tutorials are where stale
   versions go to live forever.
3. **Known pitfalls.** How do implementations of this fail? Issue trackers,
   post-mortems, and migration guides are worth more than overviews here. This is
   what turns vague non-functional requirements into specific ones.
4. **External constraints.** Rate limits, quotas, pricing tiers, licence terms,
   platform review rules, accessibility or regulatory obligations. Anything that
   caps what the thing can do regardless of how well it is built.

### How much

Scale the effort to the stakes set in the calibrate step, and stop when new searches
stop changing anything.

| stakes | searches | depth | recorded as |
|---|---|---|---|
| `hobby` | 2–4 | confirm it doesn't already exist; confirm versions | inline in the brief |
| `internal` | 4–8 | the above, plus pitfalls and any integration limits | `research.md` |
| `serious` | 8–15 | all four questions, with primary sources for each claim | `research.md` |

At `hobby` stakes there is no `research.md` and no finding IDs. Put what you found
into the brief's background and constraints with a bare URL after the claim, and
raise anything unresolved as a clarifying question. Everything below about judging
sources still applies; only the bookkeeping goes away.

If you have no web access, say so explicitly, record the internal findings only, and
mark the verdict `build` with the reason `research unavailable`. Silently skipping
this phase and drafting from recall is the failure this exists to prevent.

### Judging sources

- Prefer primary sources: official docs, the repository, the changelog, the
  regulation itself, the pricing page.
- Check the date on everything. An undated answer about a versioned thing is
  worthless.
- Two independent sources for anything load-bearing. A single blog post is a lead,
  not a finding.
- Discard listicles and content farms. If a page reads as though it was written to
  rank rather than to inform, it was.
- Record what you searched and found nothing for. A negative result is a finding,
  and it stops the next person repeating the search.

### Output

At `internal` stakes and above, write `docs/specs/<slug>/research.md` in exactly this
shape. The grammar is strict because the checker parses it.

```markdown
# Research

**Idea:** a CLI that turns meeting notes into tracker tickets
**Date:** 2026-08-01
**Verdict:** build — existing tools require a hosted service; this must run offline.

## Prior art

- F1: otter.ai and Fireflies both extract action items but only as SaaS with no local mode. (source: https://otter.ai/pricing; 2026-08-01)
- F2: No CLI on PyPI covers notes-to-tickets; searched "meeting notes ticket" and "action item extract". (source: https://pypi.org/search/?q=meeting+notes+ticket; 2026-08-01)
- F3: A shelved internal attempt exists and was dropped for lack of a Jira token story. (source: PROJ-412; 2026-08-01)

## Approach

- F4: The Jira REST v3 API creates issues in bulk via POST /rest/api/3/issue/bulk, capped at 50 per call. (source: https://developer.atlassian.com/cloud/jira/platform/rest/v3/; 2026-08-01)

## Pitfalls

- F5: Bulk issue creation partially succeeds: the endpoint returns 201 with a per-issue error array, so a naive status check silently drops issues. (source: https://developer.atlassian.com/cloud/jira/platform/rest/v3/; 2026-08-01)

## External constraints

- F6: Jira Cloud REST limits a single client to roughly 10 requests per second per tenant. (source: https://developer.atlassian.com/cloud/jira/platform/rate-limiting/; 2026-08-01)

## Open questions

- Which Jira project should tickets land in? Research cannot settle a choice only the user can make.
```

### Rules

- Findings are `F1`, `F2`, ... — sequential, no gaps, no reuse, one per line.
- Every finding ends with `(source: <url or internal reference>; <YYYY-MM-DD>)`.
  The date is when you looked, not when the source was written.
- One fact per finding. A finding that needs two sources is two findings.
- State findings as facts, not summaries of pages. "The API caps bulk creation at
  50" is a finding; "the docs discuss bulk creation" is not.
- `**Verdict:**` is `build`, `adopt`, or `extend`, with one sentence of reason.
  `adopt` means an existing thing does the job — say so before writing a brief for
  a replacement. `extend` means something here already covers part of it.
- `## Open questions` holds what research could not settle. These become the
  clarifying questions in the next step, so this section is load-bearing rather
  than a postscript. Write `- None.` if there are none.
- Cite findings from the brief by ID: a constraint justified by `F4` says so. Every
  finding should end up cited somewhere in the brief, or it was not worth recording.

---

## Generic schema

The six sections of an Implementation Brief for work that is not software — a
process, a policy, a campaign, an event, a research plan, a migration, a hiring
loop. The skeleton is the same as the software schema because the discipline is the
same: state the outcome, state the requirements testably, name the constraints, say
how you will know it worked, and fence off what you are not doing.

Draft them in this order. Draft **one section per pass**, against only the rules
listed under that section.

Required section titles, exactly:

```
Goals & Background
Requirements
Quality Bar
Resources & Constraints
Acceptance Criteria
Out of Scope
```

### 1. Goals & Background

3–6 bullets naming the desired outcomes, then one short paragraph explaining why
this is being taken on now.

- Outcomes, not activities: what becomes true when this is done.
- No mechanics — how it gets done belongs in sections 2 and 4.
- The background paragraph is where prior art belongs. If this has been tried here
  before, or a comparable process exists elsewhere, say what it didn't cover and
  cite the finding — `(F3)`.

### 2. Requirements

A numbered list `FR1`, `FR2`, ... of what must happen.

- Use the templates in [Requirement syntax](#requirement-syntax), binding
  the actor that actually acts: `THE PROCESS SHALL`, `THE REVIEWER SHALL`,
  `THE CAMPAIGN SHALL`. Every line contains `SHALL`.
- One requirement per line. No gaps, no reuse of numbers.
- Cover the main path first, then secondary steps, then at least one `IF ... THEN`
  for what happens when something goes wrong or an exception arrives.
- 5–12 requirements, scaled to the stakes.
- No quality thresholds here — those are section 3.

### 3. Quality Bar

A numbered list `NFR1`, `NFR2`, ... of the standards the work must meet: turnaround
times, accuracy, coverage, cost ceilings, compliance obligations, accessibility.

- Same `SHALL` templates as section 2.
- Each one measurable: `NFR1: THE PROCESS SHALL return a decision within 5 working
  days.` Not "should be timely".
- 3–7 items. Drop what does not matter at these stakes rather than padding.

### 4. Resources & Constraints

A definitive bullet list of what this work runs on and what it may not do: people
and roles, budget, tools and systems, data sources, dependencies on other teams,
legal or policy limits, fixed dates, and anything explicitly ruled out.

- This section is where research lands. Every named tool, vendor, regulation,
  published standard, price, and deadline comes from a finding and cites it —
  `(F4)`. Regulations and pricing move, and a misnamed obligation is worse than an
  absent one.
- Where the user expressed no preference, pick the simplest workable option and
  mark it `[ASSUMPTION]`.
- For work extending something that already exists, record how it is done today and
  treat that as binding.

### 5. Acceptance Criteria

A numbered list `AC1`, `AC2`, ... of observable checks.

- Each criterion opens with the requirement IDs it covers in brackets:
  `AC1: [FR2, FR5] ...`.
- Given/When/Then form, or "Done when ...".
- Every `FR` must appear in at least one criterion.
- At least one criterion must cover the exception or failure path.
- Verifiable by someone who was not involved — name the artifact, the number, or
  the sign-off that constitutes proof.
- 5–10 criteria.

### 6. Out of Scope

3–6 bullets excluding what this effort will not cover: adjacent teams, later
phases, related problems people will assume are included.

- One line each, no explanations.
- Name the things a reasonable person would otherwise assume you were doing.
- Where something is already handled elsewhere, exclude it here and cite the
  finding that says so.

---

## Software schema

The six sections of an Implementation Brief for software. Draft them in this order;
it is both the drafting order and the assembly order.

Draft **one section per pass**. Re-read that section's entry, draft it against only
the rules listed under it, then move to the next. The rules are deliberately kept
next to the section they govern rather than collected up front.

Required section titles, exactly:

```
Goals & Background
Functional Requirements
Non-Functional Requirements
Tech Constraints & Stack
Acceptance Criteria
Out of Scope
```

### 1. Goals & Background

3–6 bullets naming the desired outcomes, then one short paragraph of background
explaining why this is being built.

- Capability language only — no implementation details.
- Outcomes, not features: what becomes true, not what gets coded.
- The background paragraph is where prior art belongs. If comparable tools exist and
  this is being built anyway, say what they don't cover and cite the finding —
  `(F1)`. That sentence is the justification for the whole brief.

### 2. Functional Requirements

A numbered list `FR1`, `FR2`, ... of what the system does.

- Use the templates in [Requirement syntax](#requirement-syntax). Every
  line contains `SHALL`.
- One requirement per line. No gaps, no reuse of numbers.
- Cover the core happy path first, then secondary behavior, then at least one
  `IF ... THEN` for an error or edge case.
- 5–12 requirements, scaled to the stakes.
- No performance, security, or quality attributes here — those are section 3.
- No technology choices here — those are section 4.

### 3. Non-Functional Requirements

A numbered list `NFR1`, `NFR2`, ... covering only the attributes that matter at
these stakes: performance, security and auth, reliability, resource limits,
compatibility.

- Same `SHALL` templates as section 2.
- Each one concrete and measurable: `NFR2: THE SYSTEM SHALL serve the first page
  load in under 2s on LAN.` Not "should be fast".
- 3–7 items. Drop any attribute that does not matter at these stakes rather than
  padding the list.

### 4. Tech Constraints & Stack

A definitive bullet list of the technology decisions a coding agent must respect:
language and runtime, frameworks, storage, deployment target, systems to integrate
with, and anything explicitly ruled out.

- This section is where research lands. Every version number, quota, rate limit,
  pricing tier, and licence restriction comes from a finding and cites it — `(F4)`.
  A number with no finding behind it is recall, and recall is what goes stale.
- Derive choices from the user's answers. Where they expressed no preference, pick
  the simplest mainstream option and mark it `[ASSUMPTION]`.
- Name versions where a version changes the work.
- For an existing codebase this section is descriptive before it is prescriptive:
  record what the repo already uses and treat it as binding.

### 5. Acceptance Criteria

A numbered list `AC1`, `AC2`, ... of observable checks.

- Each criterion opens with the requirement IDs it covers in brackets:
  `AC1: [FR2, FR5] ...`.
- Given/When/Then form, or "Done when ...".
- Every `FR` must appear in at least one criterion.
- At least one criterion must exercise an error or edge path.
- 5–10 criteria.

### 6. Out of Scope

3–6 bullets explicitly excluding what an agent might otherwise gold-plate: extra
platforms, auth systems, scaling work, admin UIs, migrations nobody asked for.

- One line each, no explanations.
- Scale to the stated stakes — a hobby project excludes more than a serious one.
- Where an existing tool already covers something, exclude it here and cite the
  finding: "Transcription — use the vendor's API `(F2)`, don't build it."

---

## Task breakdown

The brief says what to build. `tasks.md` says in what order, and it exists because
handing an agent a whole brief at once is the most reliable way to get a sprawling,
half-finished implementation. Small ordered tasks that each cite their requirements
let the work be done, checked, and resumed one piece at a time.

### Format

Write `docs/specs/<slug>/tasks.md` in exactly this shape. The grammar is strict
because the checker parses it.

```markdown
# Tasks

Derived from [brief.md](brief.md). Each task cites the requirements it implements.

## Phase 1 — Foundation

- [ ] T1 Create the project skeleton and dependency manifest. (implements: NFR3; depends on: none)
- [ ] T2 Define the brief data model and on-disk layout. (implements: FR1; depends on: T1)

## Phase 2 — Core flow

- [ ] T3 Implement the elicitation questions with assumption defaults. (implements: FR2, FR3; depends on: T2)
- [ ] T4 Reject empty submissions with an explanatory error. (implements: FR4; depends on: T3)

## Phase 3 — Verification

- [ ] T5 Add tests covering the error paths. (implements: FR4; depends on: T4)
```

Each task line is:

```
- [ ] T<n> <what to do>. (implements: <ID list>; depends on: <task IDs or none>)
```

### Rules

- Task IDs are `T1`, `T2`, ... — sequential, no gaps, no reuse.
- `implements:` lists `FR` or `NFR` IDs that exist in the brief. Never invent one.
- `depends on:` lists earlier task IDs, or `none`. A task may only depend on a
  lower-numbered task — that is what makes the list dependency-ordered.
- Every `FR` in the brief appears in at least one task's `implements:`.
- One task is one sitting: a single coherent change an agent can finish and verify
  before moving on. If a task needs three unrelated things done, it is three tasks.
- Order by dependency, then group into `## Phase N — <name>` headings so the work
  can be stopped between phases.
- Give the last phase real verification tasks. Tests, a review pass, or a
  walkthrough against the acceptance criteria — not "make sure it works".
- 5–20 tasks. More than that means the brief is too big and should be split.

### What not to do

- Don't restate the requirement as the task. `T3 Implement FR3` tells the next
  agent nothing; name the actual change.
- Don't create a task per file. Tasks are units of behavior, not of editing.
- Don't leave a requirement uncovered because it felt implicit. The checker will
  catch it, and it is usually a sign the requirement was vague.
