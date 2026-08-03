# Software schema

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

## 1. Goals & Background

3–6 bullets naming the desired outcomes, then one short paragraph of background
explaining why this is being built.

- Capability language only — no implementation details.
- Outcomes, not features: what becomes true, not what gets coded.
- The background paragraph is where prior art belongs. If comparable tools exist and
  this is being built anyway, say what they don't cover and cite the finding —
  `(F1)`. That sentence is the justification for the whole brief.

## 2. Functional Requirements

A numbered list `FR1`, `FR2`, ... of what the system does.

- Use the templates in [requirements-syntax.md](requirements-syntax.md). Every
  line contains `SHALL`.
- One requirement per line. No gaps, no reuse of numbers.
- Cover the core happy path first, then secondary behavior, then at least one
  `IF ... THEN` for an error or edge case.
- 5–12 requirements, scaled to the stakes.
- No performance, security, or quality attributes here — those are section 3.
- No technology choices here — those are section 4.

## 3. Non-Functional Requirements

A numbered list `NFR1`, `NFR2`, ... covering only the attributes that matter at
these stakes: performance, security and auth, reliability, resource limits,
compatibility.

- Same `SHALL` templates as section 2.
- Each one concrete and measurable: `NFR2: THE SYSTEM SHALL serve the first page
  load in under 2s on LAN.` Not "should be fast".
- 3–7 items. Drop any attribute that does not matter at these stakes rather than
  padding the list.

## 4. Tech Constraints & Stack

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

## 5. Acceptance Criteria

A numbered list `AC1`, `AC2`, ... of observable checks.

- Each criterion opens with the requirement IDs it covers in brackets:
  `AC1: [FR2, FR5] ...`.
- Given/When/Then form, or "Done when ...".
- Every `FR` must appear in at least one criterion.
- At least one criterion must exercise an error or edge path.
- 5–10 criteria.

## 6. Out of Scope

3–6 bullets explicitly excluding what an agent might otherwise gold-plate: extra
platforms, auth systems, scaling work, admin UIs, migrations nobody asked for.

- One line each, no explanations.
- Scale to the stated stakes — a hobby project excludes more than a serious one.
- Where an existing tool already covers something, exclude it here and cite the
  finding: "Transcription — use the vendor's API `(F2)`, don't build it."
