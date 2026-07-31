# Generic schema

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

## 1. Goals & Background

3–6 bullets naming the desired outcomes, then one short paragraph explaining why
this is being taken on now.

- Outcomes, not activities: what becomes true when this is done.
- No mechanics — how it gets done belongs in sections 2 and 4.
- The background paragraph is where prior art belongs. If this has been tried here
  before, or a comparable process exists elsewhere, say what it didn't cover and
  cite the finding — `(F3)`.

## 2. Requirements

A numbered list `FR1`, `FR2`, ... of what must happen.

- Use the templates in [requirements-syntax.md](requirements-syntax.md), binding
  the actor that actually acts: `THE PROCESS SHALL`, `THE REVIEWER SHALL`,
  `THE CAMPAIGN SHALL`. Every line contains `SHALL`.
- One requirement per line. No gaps, no reuse of numbers.
- Cover the main path first, then secondary steps, then at least one `IF ... THEN`
  for what happens when something goes wrong or an exception arrives.
- 5–12 requirements, scaled to the stakes.
- No quality thresholds here — those are section 3.

## 3. Quality Bar

A numbered list `NFR1`, `NFR2`, ... of the standards the work must meet: turnaround
times, accuracy, coverage, cost ceilings, compliance obligations, accessibility.

- Same `SHALL` templates as section 2.
- Each one measurable: `NFR1: THE PROCESS SHALL return a decision within 5 working
  days.` Not "should be timely".
- 3–7 items. Drop what does not matter at these stakes rather than padding.

## 4. Resources & Constraints

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

## 5. Acceptance Criteria

A numbered list `AC1`, `AC2`, ... of observable checks.

- Each criterion opens with the requirement IDs it covers in brackets:
  `AC1: [FR2, FR5] ...`.
- Given/When/Then form, or "Done when ...".
- Every `FR` must appear in at least one criterion.
- At least one criterion must cover the exception or failure path.
- Verifiable by someone who was not involved — name the artifact, the number, or
  the sign-off that constitutes proof.
- 5–10 criteria.

## 6. Out of Scope

3–6 bullets excluding what this effort will not cover: adjacent teams, later
phases, related problems people will assume are included.

- One line each, no explanations.
- Name the things a reasonable person would otherwise assume you were doing.
- Where something is already handled elsewhere, exclude it here and cite the
  finding that says so.
