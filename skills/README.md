# Incipit agent skills

Portable **skills** that research an idea, turn it into a structured
**Implementation Brief**, break it into ordered tasks, and verify the result with a
script. The host agent runs the whole flow itself in the conversation — no server,
no model endpoint, no install beyond copying a directory. Any skill-capable agent
can use them.

These skills are the **authoritative definition** of the Incipit flow. The FastAPI
web app in [`../webapp/`](../webapp/) is a separate, self-contained implementation
of an earlier version of the same idea; its `app/wizard/*.yaml` are that app's own
copies and have diverged. Change the flow here.

| Skill | What it does |
|---|---|
| `incipit` | Full flow: frame → calibrate → research → clarify → draft → write files → tasks → verify |
| `incipit-clarify` | Just the decision-changing questions, each with an `[ASSUMPTION]` default |
| `incipit-review` | Audit an existing spec, PRD, or brief for gaps, risks, and scope creep |

The brief covers software by default, but the section schema is swappable, so the
same flow works for a process, a policy, a campaign, or a research plan.

## Layout

```
skills/
├── src/              # canonical source — edit here
│   ├── incipit/
│   │   ├── SKILL.md
│   │   ├── reference/     # loaded on demand
│   │   │   ├── research.md              # internal + web research protocol
│   │   │   ├── requirements-syntax.md   # the SHALL templates (EARS)
│   │   │   ├── schema-software.md       # sections for software
│   │   │   ├── schema-generic.md        # sections for everything else
│   │   │   ├── tasks.md                 # task-list format
│   │   │   └── refine.md                # per-section refine menu
│   │   └── scripts/       # stdlib-only, run not read
│   │       ├── repo_context.py          # codebase grounding
│   │       └── brief_check.py           # verification gate
│   ├── incipit-clarify/
│   └── incipit-review/
├── eval/triggers.json  # should-trigger / near-miss prompts per skill
├── harnesses.json      # per-harness frontmatter + on-disk layout
├── build.py            # generates dist/ from src/
└── dist/               # generated — do not edit
```

`src/` is the single source of truth. Harnesses differ only in frontmatter and
directory layout, so every adapter in `dist/` is generated. Hand-maintained copies
drift, which is what the build and its test exist to prevent.

## Install

Copy or symlink the adapter for your host out of `dist/`. Symlinks keep the live
skill in sync with the repo, so edits take effect immediately. Run these from the
repo root.

| Host | Adapter | Install path |
|---|---|---|
| Claude Code | `dist/claude/<skill>` | `~/.claude/skills/<skill>` |
| Cursor | `dist/cursor/<skill>` | `~/.cursor/skills/<skill>` |
| Codex | `dist/codex/<skill>` | `~/.codex/skills/<skill>` |
| OpenClaw | `dist/openclaw/<skill>` | `~/.openclaw/skills/<skill>` |
| Hermes Agent | `dist/hermes/software-development/<skill>` | `~/.hermes/skills/software-development/<skill>` |
| Anything reading `AGENTS.md` | `dist/agents/AGENTS.md` | your project root |

```bash
# Claude Code (all three skills, globally)
mkdir -p ~/.claude/skills
for s in incipit incipit-clarify incipit-review; do
  ln -s "$PWD/skills/dist/claude/$s" ~/.claude/skills/"$s"
done

# Cursor
mkdir -p ~/.cursor/skills
for s in incipit incipit-clarify incipit-review; do
  ln -s "$PWD/skills/dist/cursor/$s" ~/.cursor/skills/"$s"
done
```

Prefer copies? Replace `ln -s` with `cp -r`.

Claude Code and Cursor also support per-project skills — place them under a repo's
`.claude/skills/<skill>` or `.cursor/skills/<skill>` to share them with a team via
version control.

> **Cursor:** user skills go in `~/.cursor/skills/`. Do not install into
> `~/.cursor/skills-cursor/` — that directory is reserved for Cursor's built-in
> skills and is managed automatically.

> **Hermes:** Hermes tracks *bundled* skills in `~/.hermes/skills/.bundled_manifest`.
> A user skill dropped under an existing category directory (here,
> `software-development/`) is discovered without touching that manifest.

The `AGENTS.md` fallback is for hosts that read always-on instructions but don't
support invocable skills. It inlines all three skills plus their reference files
into one document. Prefer the real skills wherever the host supports them.

## Use

Ask the host agent to "spec this out with incipit" (or invoke the skill by name)
and describe your idea. It calibrates, researches what already exists, asks the
clarifying questions, drafts the sections one at a time, and writes:

```
docs/specs/<slug>/research.md   # findings, each with a source and a date
docs/specs/<slug>/brief.md      # the Implementation Brief, citing those findings
docs/specs/<slug>/tasks.md      # dependency-ordered tasks, each citing its requirements
```

How much ceremony you get scales with the stakes it infers. A `hobby` idea gets one
file: the research goes into the brief's background with bare URLs, and the task list
becomes a checklist at the end. `internal` and `serious` get all three, with IDs and
full traceability. The research and the searching happen either way — only the
bookkeeping scales.

For a hands-off run, say "shoot the moon" — it fills every blank with the
`[ASSUMPTION]` default and goes straight through to the verified files.

For an existing codebase, point it at the repo. The skill runs
`scripts/repo_context.py` to summarize the real stack, layout, and declared
commands so the constraints match what the code already does, and searches the
tracker and git history for work already done or already rejected.

Research can end the flow early. If it finds something that already does the job,
the verdict is `adopt` and you get told that instead of a brief for a redundant
build — including under "shoot the moon".

You can run the verification gate yourself on any brief, whether an agent wrote it
or you did:

```bash
python3 skills/src/incipit/scripts/brief_check.py docs/specs/<slug>/brief.md \
  --tasks docs/specs/<slug>/tasks.md --research docs/specs/<slug>/research.md
```

Both optional arguments can be left off, which is what makes the `hobby` path work.
Adding `--verify-sources` also fetches every cited URL and fails on the dead ones; it
is opt-in because citation *format* is verifiable offline and citation *existence*
is not.

It checks structure, requirement syntax, ID references, citation format,
acceptance-criteria coverage, and task dependency ordering. It deliberately says
nothing about whether the content is any good — that is what `incipit-review` is
for.

Three traceability links are enforced, each in both directions: findings to the
brief, requirements to acceptance criteria, and requirements to tasks. An
uncited finding, an uncovered requirement, and an unimplemented requirement are all
caught, so evidence cannot be gathered and then quietly dropped.

## Develop

Edit `src/`, then regenerate and verify:

```bash
python3 build.py            # regenerate dist/
python3 build.py --check    # fail if dist/ is stale
pytest                      # from this directory
```

Everything here is standalone: `build.py` and both bundled scripts use only the
standard library, and the tests import nothing from the web app, so this directory
can be lifted out of the repo and still build and verify itself. The tests fail
when `dist/` is stale, when a skill body diverges between harnesses, when a
`reference/` link is dead, when a body outgrows its 500-line budget, when
`brief_check.py` would pass a brief it should reject, or when a skill has no
trigger-eval prompts.

To support a new harness, add an entry to `harnesses.json` and rebuild — no new
skill copy to maintain.

### Changing a description

The `description` in the frontmatter is the only text a host matches against when
deciding whether to load a skill, which makes it the highest-leverage thing in the
file and the easiest to break. After changing one, run the prompts in
`eval/triggers.json` against a real host and confirm from the transcript that the
skill loaded — `should_trigger` prompts must load it and `near_miss` prompts must
not. The test suite only checks that the eval set stays well-formed and covers
every skill; it cannot tell you whether a description works.

### Why the flow looks the way it does

Two constraints shaped it, and both are easy to undo by accident:

- **Sections are drafted one per pass, with each section's rules stated next to
  it.** Compositional instruction-following degrades sharply past five or six
  simultaneous constraints, and cross-referencing rules are the first to be
  dropped. Collecting all the rules into one up-front list would read better and
  work worse.
- **Requirements use fill-in-the-blank `SHALL` templates.** "Write a testable
  requirement" is a judgment a model silently fails; "the line contains SHALL" is
  something `brief_check.py` can confirm. The templates exist to make verification
  mechanical, which is also why the error-path rule is expressed as the
  `IF ... THEN` pattern rather than as advice to consider edge cases.
- **Research is a phase with an artifact, not a step inside drafting.** Findings
  have IDs and citations so the brief can point at evidence rather than assert from
  recall, and so a stale version number is a traceable mistake instead of an
  anonymous one. It runs after calibration because its budget is set by the stakes,
  and before the clarifying questions because a question research can answer should
  never reach the user.
- **Artifacts scale with stakes; rigor of thought does not.** The `hobby` path drops
  `research.md` and `tasks.md`, not the searching or the acceptance criteria. This
  skill exists to compress, and a flow that costs three files for a weekend script
  fails at the thing it is for.
