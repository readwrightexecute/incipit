# Incipit

*"here begins"* — turn a rough idea into a structured **Implementation Brief**
before any work starts. Instead of hoping you remembered to specify everything,
Incipit interrogates the idea for you: it researches what already exists, infers the
stakes and form factor, asks only the questions research couldn't answer, drafts the
spec a section at a time, breaks it into ordered tasks, and verifies the result with
a script before handing it over.

You get files an agent can execute against — `brief.md`, plus `research.md` and
`tasks.md` once the stakes justify them — rather than a wall of chat to copy out.
Findings carry sources and dates, and the brief cites them, so a version number or a
rate limit in the spec is evidence rather than recall. It defaults to software, but
the section schema is swappable, so the same flow works for a process, a policy, or a
research plan.

```
skills/    portable agent skills — the flow, for any coding agent   (start here)
webapp/    a local FastAPI + HTMX wizard driving your own model endpoint
```

## Agent skills

Three skills that any skill-capable agent can run — Claude Code, Cursor, Codex,
OpenClaw, Hermes, and anything that reads `AGENTS.md`. No server, no model
endpoint, no dependencies; the agent runs the flow itself in the conversation.

| Skill | What it does |
|---|---|
| `incipit` | Full flow: research → calibrate → clarify → draft → write the three files → verify |
| `incipit-clarify` | Just the decision-changing questions, each with an `[ASSUMPTION]` default |
| `incipit-review` | Audit an existing spec, PRD, or brief for gaps, risks, and scope creep |

### Install

The easiest path is to let your agent do it. From a checkout, ask it:

> Install the Incipit skills for this agent, following AGENTS.md.

[`AGENTS.md`](AGENTS.md) gives it the host-to-path table, the build check, and the
verification step.

To do it yourself, copy or symlink the adapter for your host out of
`skills/dist/`:

```bash
# Cursor, globally — swap `cursor` for claude / codex / openclaw
mkdir -p ~/.cursor/skills
for s in incipit incipit-clarify incipit-review; do
  ln -sfn "$PWD/skills/dist/cursor/$s" ~/.cursor/skills/"$s"
done
```

| Host | Install to |
|---|---|
| Claude Code | `~/.claude/skills/<skill>` or `.claude/skills/<skill>` per project |
| Cursor | `~/.cursor/skills/<skill>` or `.cursor/skills/<skill>` per project |
| Codex | `~/.codex/skills/<skill>` |
| OpenClaw | `~/.openclaw/skills/<skill>` |
| Hermes Agent | `~/.hermes/skills/software-development/<skill>` |
| Anything reading `AGENTS.md` | copy `skills/dist/agents/AGENTS.md` to your project root |

Most hosts need a new session to discover the skills. Full details, including
per-host cautions and uninstall, are in [`skills/README.md`](skills/README.md).

### Use

Say "spec this out with incipit" and describe your idea. It infers the stakes and
form factor, researches prior art and what's already been tried, asks the handful of
questions research couldn't settle (each with a default you can ignore), drafts the
sections one at a time, and writes the artifacts under `docs/specs/<slug>/`. For a
hands-off run, say "shoot the moon". Point it at a repo and it reads the real stack,
the tracker, and the git history first, so the constraints match what you already
have.

A weekend script gets one file; a production service gets three with full
requirement traceability. The stakes it infers decide, so the ceremony matches what
you're actually building.

If research finds something that already does the job, you get told that instead of
a brief for a redundant build.

Nothing is handed over until `scripts/brief_check.py` passes, which verifies
structure, requirement syntax, citation format, requirement-to-criterion coverage,
and task ordering — the checks an agent is least reliable at doing by rereading its
own output.

`skills/` is the authoritative definition of the flow and is standalone — standard
library only, no dependency on the web app.

## Web app

A local wizard that runs the same flow against any OpenAI-compatible endpoint
(Ollama, LM Studio, llama.cpp, vLLM, OpenAI), with SSE progress and a downloadable
brief. It is fully self-contained under `webapp/`.

```bash
cd webapp
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8911
```

See [`webapp/README.md`](webapp/README.md) for configuration, the round-table
review, and the optional GPU DiffusionGemma backend.

## Repo layout

| Path | What |
|---|---|
| `skills/src/` | canonical skill sources — edit here |
| `skills/dist/` | generated per-harness adapters — do not edit |
| `skills/build.py` | regenerates `dist/`; `--check` fails when stale |
| `webapp/` | the FastAPI app, its tests, container build, and docs |
| `AGENTS.md` | instructions for agents working in this repo |

The two halves are independent and verify separately:

```bash
cd skills && pytest    # 108 tests, standard library only
cd webapp && pytest    # 215 tests, offline, with a scoped coverage gate
```

## License

MIT — see [`LICENSE`](LICENSE).
