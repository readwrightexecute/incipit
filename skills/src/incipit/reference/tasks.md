# Task breakdown

The brief says what to build. `tasks.md` says in what order, and it exists because
handing an agent a whole brief at once is the most reliable way to get a sprawling,
half-finished implementation. Small ordered tasks that each cite their requirements
let the work be done, checked, and resumed one piece at a time.

## Format

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

## Rules

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

## What not to do

- Don't restate the requirement as the task. `T3 Implement FR3` tells the next
  agent nothing; name the actual change.
- Don't create a task per file. Tasks are units of behavior, not of editing.
- Don't leave a requirement uncovered because it felt implicit. The checker will
  catch it, and it is usually a sign the requirement was vague.
