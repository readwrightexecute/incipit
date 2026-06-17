# Product

## Register

product

## Users

Technical users running Incipit with their own model endpoint — internal/work
colleagues, developers, and anyone who has cloned it (the "bring your own model"
path: Ollama, LM Studio, llama.cpp, vLLM, OpenAI). They arrive with a rough,
half-formed software idea and want a rigorous, paste-ready spec for a coding
agent without writing it by hand. They're comfortable with a terminal and an
endpoint/model settings panel; they value speed and signal over hand-holding,
but a newcomer must still be able to follow the flow on first run.

The job to be done: **turn a brain dump into a single structured "mega-prompt"
in minutes** — calibrate stakes/form-factor, answer one batch of clarifying
questions (with smart `[ASSUMPTION]` defaults), draft and refine six spec
sections, optionally run a "round table" review, then copy/download the result.

## Product Purpose

A BMAD-style mega-prompt wizard. It compresses the elicitation a good spec needs
(idea → calibrate → clarify → sections → final) into a fast, mostly hands-off
flow, and assembles the final spec deterministically (no LLM call). It exists so
that the quality of a coding-agent prompt doesn't depend on the user remembering
to ask themselves every question. Success = the user pastes the output into an
agent and it has what it needs, on the first try, without a back-and-forth.

Model-agnostic by design: it talks to any OpenAI-compatible endpoint and has an
advanced local DiffusionGemma path. No authentication — localhost / trusted
network only.

## Brand Personality

**Terminal-native craft** — precise, technical, hacker-tool confidence. Three
words: *precise, transparent, unfussy.* The voice is a capable CLI, not a
chat-bot: it shows the machine working (live SSE progress, a ❯ shell prompt,
monospace activity blocks) rather than hiding behind vague spinners. Some energy
and personality are welcome (the violet glow, the "Shoot the Moon" hands-off
mode, the round-table "party"); the line is that energy must read as *craft*,
never as marketing.

## Anti-references

- **Generic AI-SaaS look** — gradient text, hero-metric blocks, endless
  identical icon+heading card grids, decorative glassmorphism. The default
  AI-startup aesthetic is the thing to actively avoid.
- **Corporate / enterprise dashboard** — heavy chrome, business-blue palette,
  data-table-everywhere density, admin-panel coldness.
- **Childish / over-friendly** — cartoon illustrations, mascots, rounded
  consumer-app cuteness, emoji as decoration. (Functional emoji as state/wayfinding
  markers — 🌙 moonshot, 🎉 round table, ✓ applied — are fine; decorative ones aren't.)

(Note: "loud / attention-grabbing" was *not* ruled out — controlled energy is
on-brand, as long as it isn't marketing-landing energy on a working tool.)

## Design Principles

1. **Compression over completeness.** The product's whole value is respecting the
   user's time. Default smart assumptions, never force a blank the user doesn't
   care about, and keep every step to the minimum that earns its place.
2. **Show the machine working.** Generation is slow and asynchronous; make that
   legible and even satisfying (terminal progress, heartbeat, the round-table
   transcript) instead of papering over it. Transparency is the feature.
3. **Tool, not toy.** Assume a technical user: density, keyboard-friendliness,
   and confidence over tutorialization — while keeping first-run legible to a
   stranger who just cloned it.
4. **Unambiguous state.** Pending / applying / applied / denied, and finding
   severity, must be readable at a glance. The user is making
   approve/deny decisions; never make them guess what state something is in.
5. **Bring your own everything.** Stay provider-agnostic in copy and UI. Never
   assume a specific model, vendor, or that thinking-mode behaves one way.

## Accessibility & Inclusion

Target **WCAG 2.1 AA**. Dark-theme by design, so body text holds ≥4.5:1 and
large text ≥3:1; keyboard navigation and visible focus on all controls;
`prefers-reduced-motion` honored for the always-on terminal/heartbeat motion;
live regions (`role="status"` / `aria-live`) on the SSE-driven progress and
round-table panels so non-visual users get the async updates. Severity/state is
never carried by color alone — pair it with a label or icon.
