# Incipit as an agent skill

These are portable **skill** versions of Incipit for three host agents. Instead of
running the FastAPI web app against a model endpoint, each skill makes the host agent
*itself* run Incipit's flow — `calibrate → clarify → draft six sections → assemble` —
directly in the conversation, producing the same **Implementation Brief** the web app
emits. No server, no separate model endpoint.

All three share one canonical body (ported from `app/wizard/sections.yaml`,
`elicitation.yaml`, and `prompts/*.md.j2`); they differ only in frontmatter. Each is
self-contained — copy the `SKILL.md` out of the repo and it still works.

| Agent | File | Frontmatter |
|---|---|---|
| Claude / Claude Code | `claude/incipit/SKILL.md` | `name`, `description` |
| Cursor | `cursor/incipit/SKILL.md` | `name`, `description` |
| Hermes | `hermes/software-development/incipit/SKILL.md` | superset (`version`, `author`, `license`, `platforms`, `metadata.hermes.*`) + Common Pitfalls / Verification Checklist sections |

The Claude and Cursor bodies are identical; the Hermes body is a superset following
Hermes' skill-authoring conventions.

## Install (symlink — repo stays the source of truth)

Run from the repo root. Symlinks keep the live skills in sync with the repo; edits
here take effect immediately.

```bash
# Claude Code (global user skills)
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/claude/incipit" ~/.claude/skills/incipit

# Cursor (global skills)
ln -s "$PWD/skills/cursor/incipit" ~/.cursor/skills-cursor/incipit

# Hermes (user skills, software-development category)
ln -s "$PWD/skills/hermes/software-development/incipit" \
      ~/.hermes/skills/software-development/incipit
```

Prefer copies over symlinks? Replace each `ln -s` with `cp -r`.

For Claude Code you can also install this per-project by placing the skill under a
repo's `.claude/skills/incipit/`.

> **Hermes note:** Hermes tracks *bundled* skills in
> `~/.hermes/skills/.bundled_manifest`. A user skill dropped under an existing
> category directory (here, `software-development/`) is discovered without touching
> that manifest — no manifest edit needed.

## Use

Ask the host agent to "spec this out with incipit" (or invoke the skill by name) and
describe your idea. It will calibrate, ask the clarifying questions, draft the six
sections, and hand back the assembled Implementation Brief. For a hands-off run, say
"shoot the moon" — it fills every blank with the `[ASSUMPTION]` default and returns
the finished brief in one pass.
