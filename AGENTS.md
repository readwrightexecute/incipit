# AGENTS.md

Instructions for an agent working in this repository.

This repo contains two independent halves. They share no code, and each verifies
itself without the other.

1. **`skills/`** — portable agent skills that turn a rough software idea into a
   structured Implementation Brief. The authoritative definition of the Incipit
   flow, and what most people want. Standard library only.
2. **`webapp/`** — a FastAPI + HTMX web app implementing the same idea against an
   OpenAI-compatible model endpoint. Self-contained, including its own tests,
   container build, and docs; see [`webapp/AGENTS.md`](webapp/AGENTS.md).

Keep them isolated: never make `skills/` depend on `webapp/`, or the reverse.

> Do not confuse this file with `skills/dist/agents/AGENTS.md`. That one is a
> *generated artifact* users copy into their own project to get the Incipit flow
> on a host that lacks skill support. This file is guidance for working here.

## Task: install the skills for the user

When a user asks you to install, set up, or add the Incipit skills, follow this.
It is a file copy — there is nothing to compile and no dependency to install.

### 1. Identify the host and target path

| Host | Adapter to install from | Install to |
|---|---|---|
| Claude Code | `skills/dist/claude/<skill>` | `~/.claude/skills/<skill>` |
| Cursor | `skills/dist/cursor/<skill>` | `~/.cursor/skills/<skill>` |
| Codex | `skills/dist/codex/<skill>` | `~/.codex/skills/<skill>` |
| OpenClaw | `skills/dist/openclaw/<skill>` | `~/.openclaw/skills/<skill>` |
| Hermes Agent | `skills/dist/hermes/software-development/<skill>` | `~/.hermes/skills/software-development/<skill>` |
| Any host that reads `AGENTS.md` | `skills/dist/agents/AGENTS.md` | the user's project root |

The three skills are `incipit`, `incipit-clarify`, and `incipit-review`. Install
all three unless the user asks for a subset.

If you cannot tell which host you are running in, ask. Do not guess and write to
several paths.

### 2. Choose global or per-project

Default to **global** (the `~/...` paths above) so the skills work everywhere.
Claude Code and Cursor also support per-project skills at `.claude/skills/<skill>`
and `.cursor/skills/<skill>`, which is the right choice when the user wants the
skills committed and shared with a team.

### 3. Make sure `dist/` is current

```bash
python3 skills/build.py --check || python3 skills/build.py
```

`skills/dist` is generated from `skills/src`. If the check fails, rebuild before
installing or you will ship a stale skill.

### 4. Install

Symlink when the user has a checkout they will keep, so repo edits take effect
immediately:

```bash
mkdir -p ~/.cursor/skills
for s in incipit incipit-clarify incipit-review; do
  ln -sfn "$PWD/skills/dist/cursor/$s" ~/.cursor/skills/"$s"
done
```

Copy instead when the checkout is temporary or the user wants the skills
committed to their own repo:

```bash
mkdir -p ~/.cursor/skills
for s in incipit incipit-clarify incipit-review; do
  cp -r "skills/dist/cursor/$s" ~/.cursor/skills/"$s"
done
```

Substitute the adapter directory and install path for the user's host from the
table above. Hermes needs the `software-development/` category directory to exist;
`mkdir -p ~/.hermes/skills/software-development` first.

### 5. Verify and report

Confirm `SKILL.md` landed where you expect, then tell the user the skills are
installed and how to invoke them:

```bash
ls -l ~/.cursor/skills/incipit/SKILL.md
```

Most hosts need a restart or a new session to discover new skills — say so. Then
report the three skill names and that the user can say "spec this out with
incipit" or invoke a skill by name.

### Host-specific cautions

- **Cursor:** user skills go in `~/.cursor/skills/`. Never write to
  `~/.cursor/skills-cursor/` — that path is reserved for Cursor's built-in skills
  and is managed automatically.
- **Hermes:** bundled skills are tracked in `~/.hermes/skills/.bundled_manifest`.
  A user skill placed under an existing category directory is discovered without
  editing that manifest, so do not touch it.
- **Hosts without skill support:** copy `skills/dist/agents/AGENTS.md` into the
  user's project root instead. It inlines all three skills and their reference
  files into one always-on document. Prefer real skills wherever supported.

### Uninstall

| Host | Remove |
|---|---|
| Claude Code | `~/.claude/skills/incipit*` |
| Cursor | `~/.cursor/skills/incipit*` |
| Codex | `~/.codex/skills/incipit*` |
| OpenClaw | `~/.openclaw/skills/incipit*` |
| Hermes Agent | `~/.hermes/skills/software-development/incipit*` |
| `AGENTS.md` fallback | delete the copied `AGENTS.md` |

Nothing is written outside these paths, so removal is complete.

## Task: change the skills

Edit `skills/src/` — never `skills/dist/`, which is generated and overwritten.

```bash
python3 skills/build.py          # regenerate dist/
python3 skills/build.py --check  # fail if dist/ is stale
cd skills && pytest              # 107 tests, standalone
```

Rules that the tests enforce, so you will find out if you break them:

- A skill body must stay under 500 lines; detail belongs in `reference/`, which
  the agent loads on demand.
- Skill bodies must be identical across harnesses. Only frontmatter and layout may
  differ, and both come from `skills/harnesses.json`.
- Every `reference/` link must resolve to a real file.
- Every `scripts/*.py` a skill body tells the agent to run ships inside that
  skill's own directory (see `shared_files` in `skills/harnesses.json`).
- `skills/dist` must match `skills/src`.
- Every skill has trigger-eval prompts in `skills/eval/triggers.json` and a
  `Do not use` clause in its description.
- `brief_check.py` rejects every malformed brief it claims to reject.

Two design decisions in `skills/src/incipit/` are load-bearing and easy to undo
while "tidying up":

- Each section's drafting rules live next to that section in the schema file, and
  sections are drafted one per pass. Models stop reliably honouring constraints
  past about five or six at once, so consolidating the rules into one list would
  read better and work worse.
- Requirements use the `SHALL` templates in `reference/requirements-syntax.md`
  because that is what makes `scripts/brief_check.py` able to verify them. Relaxing
  the templates silently disables the verification gate.
- The research phase runs after calibration and before the clarifying questions. Its
  budget is set by the stakes, so it cannot move earlier; its findings become the
  questions, so it cannot move later. Folding it into drafting would reintroduce
  specs written from a training cutoff.
- The stakes ladder in the calibrate step drops `research.md` and `tasks.md` at
  `hobby`, and both checker arguments are optional so that path verifies cleanly.
  What it never drops is the searching or the acceptance criteria — the artifacts
  scale, the thinking doesn't.

To support a new harness, add an entry to `skills/harnesses.json` and rebuild. Do
not hand-write another skill copy.

Keep `skills/` standalone: standard library only, and no imports from `app/`. The
subtree is meant to be liftable out of this repo, and its tests verify that.

## Task: change the web app

See [`webapp/AGENTS.md`](webapp/AGENTS.md) and run everything from `webapp/`. Note
that `webapp/app/wizard/*.yaml` holds the app's own copy of the section schema; it
is deliberately forked from the skills and nothing syncs the two. A change to the
*flow itself* belongs in `skills/src/`.

## Verifying

There is no repo-wide test command by design — each half stands alone.

```bash
cd skills && pytest                                     # 107 tests, stdlib only
cd webapp && pip install -r requirements-dev.txt && pytest   # 118 tests, offline
```
