# Research protocol

Before specifying anything, find out what already exists. The most expensive brief
is a well-written one for something that was already solved, already tried here and
abandoned for a reason, or blocked by a constraint nobody looked up.

This phase answers four questions and writes the answers down with citations, so
the brief rests on recorded evidence instead of model recall. Recall is the problem:
model training data has a cutoff, and library versions, pricing, API limits, and
regulations all move after it.

Research has two halves. Do the internal half first — it is cheaper, and it often
ends the research early.

## Internal: what has already been done here

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

## External: what exists in the world

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

## How much

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

## Judging sources

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

## Output

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

## Rules

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
