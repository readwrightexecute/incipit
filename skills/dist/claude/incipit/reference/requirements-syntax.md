# Requirement syntax

Every requirement in a brief is written with one of five templates. This is EARS —
the Easy Approach to Requirements Syntax, developed at Rolls-Royce and presented at
IEEE RE09 — and it is not decoration. "Write a testable requirement" is a judgment
call that gets dropped under load; "start the line with WHEN and include SHALL" is
a form you either filled in or didn't, and the checker can tell the difference.

The templates also force you to name things you would otherwise leave implicit: the
trigger, the actor, and the observable result.

## The five templates

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

## Examples

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

## Numbering and references

- Functional requirements are `FR1`, `FR2`, ... — one per line, no gaps, no reuse.
- Non-functional requirements are `NFR1`, `NFR2`, ... on the same terms.
- Every acceptance criterion begins with the IDs it covers in square brackets:
  `AC1: [FR2, FR5] ...`. Every FR must be covered by at least one criterion.

The bracketed prefix exists so coverage is mechanically checkable. Prose like
"this criterion relates to the export requirement" is not.

## Coverage floor

Whatever the stakes, a brief must contain **at least one `IF ... THEN`
requirement**. A spec with only happy-path behavior has not been thought through,
and since every requirement must also be covered by a criterion, one unwanted-
behavior requirement guarantees one error-path check.

This is why the error path is expressed as a template rather than as an
instruction to "consider edge cases": the template is something the checker can
confirm, and an instruction is something it cannot.
