---
name: Incipit
description: A BMAD-style mega-prompt wizard — idea → structured spec, terminal-native.
colors:
  violet: "#bb9af7"
  violet-deep: "#7c5cd6"
  violet-hover-bg: "#8d6ee6"
  bg: "#16161f"
  surface: "#1e1f2e"
  terminal-bg: "#0b0b12"
  ink: "#c6cbe3"
  ink-strong: "#efedf7"
  terminal-fg: "#c8d3f5"
  muted: "#7e86ac"
  border: "#2a2c3e"
  field-bg: "#1a1b28"
  field-border: "#313450"
  danger: "#f7768e"
  warning: "#e0af68"
  info: "#7aa2f7"
  success: "#9ece6a"
typography:
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "'Departure Mono', ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.12em"
rounded:
  sm: "8px"
  bubble: "10px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.violet-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "0.75rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.violet-hover-bg}"
    textColor: "#ffffff"
  seg-button:
    backgroundColor: "{colors.field-bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 0.85rem"
  seg-button-selected:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0.12rem 0.6rem"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "1rem"
  input:
    backgroundColor: "{colors.field-bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  terminal-block:
    backgroundColor: "{colors.terminal-bg}"
    textColor: "{colors.terminal-fg}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.6rem 0.9rem 0.6rem 2rem"
---

# Design System: Incipit

## 1. Overview

**Creative North Star: "The Lit Terminal"**

Incipit looks like a dark operator's console with the machine's work glowing
through it. The surface is a near-black violet-tinted void; the one warm light is
a soft violet glow bleeding in from the top-right corner. Where the system is
*doing* something — generating a section, running the round table — it speaks in a
monospace terminal block with a ❯ shell prompt and a blinking block cursor. The
aesthetic philosophy is **transparency as craft**: nothing hides behind a vague
spinner; the user watches the elicitation happen and trusts the result because
they saw it built.

Density is deliberate and technical. This is a tool, not a landing page — it
assumes a user who is comfortable at a terminal, optimizes for their speed, and
spends its personality budget on a few committed moments (the violet glow, the
🌙 "Shoot the Moon" mode, the 🎉 round-table dock) rather than spreading thin
decoration across every section. Controlled energy is welcome; marketing energy
is not.

It explicitly rejects the **generic AI-SaaS look** (gradient text, hero-metric
blocks, identical icon-card grids, decorative glass), the **corporate dashboard**
(business-blue, heavy chrome, admin-panel coldness), and anything **childish**
(mascots, cartoon illustration, emoji-as-decoration).

**Key Characteristics:**
- Dark, violet-tinted void (`#16161f`) with a single corner glow as the only "warmth."
- One accent hue: violet (`#bb9af7` / `#7c5cd6`). No competing brand colors.
- Monospace (Departure Mono) reserved for the machine's voice — terminals, labels, severity tags.
- Tonal layering, not shadows, for depth. Shadows appear only on things that float.
- Tokyo Night status palette (red/yellow/blue/green) for state, never as decoration.

## 2. Colors

A single violet accent over a near-black violet-tinted neutral ramp, with a
four-color Tokyo Night status set reserved strictly for state.

### Primary
- **Lumen Violet** (`#bb9af7`): The one accent. Links, focused borders, the ❯
  shell prompt and block cursor, selected-state rings, chip hover. Its scarcity
  is the point — it marks what's interactive or alive, nothing else.
- **Deep Violet** (`#7c5cd6`): Solid fills — the primary button, the floating
  dock header. Also the source of the top-right body glow (at low alpha).

### Neutral
- **Void** (`#16161f`): The body background. Near-black with a violet tint, never a true gray.
- **Surface** (`#1e1f2e`): Cards, bubbles, the settings region — one step up from the void.
- **Terminal Black** (`#0b0b12`): Darker than the body. Reserved for terminal/activity blocks so the machine's voice recedes into its own well.
- **Reading Violet** (`#c6cbe3`): Body text. **Strong White-Violet** (`#efedf7`) for h1.
- **Muted Slate** (`#7e86ac`): Hints, assumptions, meta. Measured at ~5:1 on Void — the floor, not below it.
- **Hairline** (`#2a2c3e`): Borders and dividers.

### Status (state only — never decorative)
- **Danger Red** (`#f7768e`): errors, denied state, high-severity findings.
- **Warning Amber** (`#e0af68`): medium severity, the facilitator's voice in chat.
- **Info Blue** (`#7aa2f7`): low-severity findings.
- **Success Green** (`#9ece6a`): applied state, info-level findings, "✓ done" confirmations.

### Named Rules
**The One Accent Rule.** Violet is the only brand color. If a second hue appears
on screen and it isn't one of the four status colors carrying actual state, it's
wrong. "Warmth" comes from the corner glow and the violet itself, never from a
warm-tinted background.

**The State-Color Rule.** Red/amber/blue/green mean *something happened*. They
are forbidden as decoration, as section accents, or as palette variety.

## 3. Typography

**Display / Body Font:** System UI sans (`system-ui, -apple-system, "Segoe UI", Roboto, …`) — Pico's default stack.
**Label / Mono Font:** Departure Mono (self-hosted, OFL) with a `ui-monospace` fallback chain.

**Character:** A clean, invisible system sans does the reading work; the
monospace does the *machine's* talking. The pairing contrast is functional, not
stylistic — mono is a signal ("this is the program speaking"), not a flavor.

### Hierarchy
- **Display** (700, 2rem, letter-spacing -0.02em): The "Incipit" wordmark / page h1. Tightened tracking gives it a compact, set-not-shouting feel.
- **Headline** (600, ~1.5rem): Section headings (h2).
- **Title** (600, 1rem): Card headers (h3) — kept at body size on purpose; cards are dense, not billboards.
- **Body** (400, 1rem, line-height 1.5): All prose, form text, generated spec content.
- **Label** (600 mono, 0.75rem, letter-spacing 0.12em, UPPERCASE): Step labels ("STEP 1 OF 3"), severity tags. Mono + tracking marks system/wayfinding text.

### Named Rules
**The Two-Step Rule.** UI text lives on exactly three sizes: 12px (`--fs-xs`),
14px (`--fs-sm`), 16px (body). Hierarchy is carried by weight, color, and the
heading scale — never by inventing a fourth in-between size.

**The Mono-Means-Machine Rule.** Departure Mono is reserved for the program's own
voice (terminals, labels, severity codes). Don't set prose or buttons in mono for
"terminal flavor"; that dilutes the signal.

## 4. Elevation

Depth is **tonal, not cast**. The three-step ramp — Void (`#16161f`) → Surface
(`#1e1f2e`) → Terminal Black (`#0b0b12`) — does the layering; flat surfaces sit
at rest with a 1px hairline border, no shadow. Shadows are reserved for things
that genuinely float above the page.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 12px 34px rgba(0,0,0,.5)`): The party-chat dock — a true floating overlay.
- **Inset Glow** (`box-shadow: inset 0 0 0 1px rgb(var(--glow-rgb) / .06)`): The faint violet inner edge on terminal blocks — atmosphere, not elevation.
- **Scrim** (`rgba(0,0,0,.6)`) + **backdrop blur(6px)**: Modal backdrop and the fixed action bar only.

### Named Rules
**The Flat-At-Rest Rule.** Cards, findings, and inputs are flat with a hairline
border. If something has a drop shadow, it must literally float (dock, modal,
sticky bar). A resting card with a shadow is a 2014 tell.

## 5. Components

### Buttons
- **Shape:** Gently rounded (8px / `--pico-border-radius`).
- **Primary:** Deep Violet fill (`#7c5cd6`), white text, ~`0.75rem 1rem` padding.
- **Hover / Focus:** Lighter violet fill (`#8d6ee6`); visible focus ring via the violet focus color. Transitions ~0.12s.
- **Secondary / Contrast:** Pico `.secondary outline` (hairline, muted) and `.contrast` (used for "🌙 Shoot the Moon") — secondary actions never compete with the primary fill.

### Chips (refine examples / history actions)
- **Style:** Pill (999px), transparent fill, hairline border, muted text.
- **State:** Hover lifts to violet border + violet text + faint violet tint (`rgb(var(--accent-rgb) / .08)`). On touch, a ≥44px hit area is enforced.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** Surface (`#1e1f2e`).
- **Shadow Strategy:** None at rest (see Elevation — Flat-At-Rest).
- **Border:** 1px Hairline (`#2a2c3e`).
- **Internal Padding:** ~1rem.

### Inputs / Fields
- **Style:** Field-bg (`#1a1b28`), Field-border (`#313450`), 8px radius.
- **Focus:** Border shifts to violet (`#bb9af7`) with a soft violet glow (`rgba(187,154,247,.35)`).
- **Segmented selectors:** `seg-btn` radio cards — selected state = violet tint background + inset violet ring + violet border. The radio input is visually hidden; the whole card is the target, with a `:focus-visible` outline.

### Signature: The Terminal / Activity Block
The defining component. Terminal Black well (`#0b0b12`), Departure Mono, a violet
❯ prompt absolutely positioned at the left, and a blinking violet block cursor
(`▋`) trailing the content. Used for live SSE progress (`#status-bar`), the
"implementing fixes" heartbeat, and any place the program narrates its own work.
It carries `role="status"` / `aria-live="polite"` so the narration reaches
non-visual users, and its blink is suppressed under `prefers-reduced-motion`.

### Signature: The Round-Table Dock
A fixed, collapsible chat dock (bottom-right, Deep Violet header) that pops up
like a browser chat widget during the "party" review. Bubbles animate in
(`bubble-in`, translateY+opacity); the facilitator's bubble is accented with a
violet border + faint tint and an amber name.

## 6. Do's and Don'ts

### Do:
- **Do** keep violet the only accent; let the four status colors carry state and nothing else (**The One Accent Rule** / **The State-Color Rule**).
- **Do** use the terminal block whenever the program is working — show the machine, don't mask it with a generic spinner.
- **Do** layer with the Void → Surface → Terminal-Black tonal ramp; keep resting surfaces flat with a 1px hairline (**The Flat-At-Rest Rule**).
- **Do** hold UI text to 12 / 14 / 16px and carry hierarchy with weight and color (**The Two-Step Rule**).
- **Do** signal state with a full border + faint tint (and a label/icon), never with color alone — keep it WCAG AA and colorblind-safe.
- **Do** reserve Departure Mono for the machine's voice (**The Mono-Means-Machine Rule**).

### Don't:
- **Don't** ship the **generic AI-SaaS look** — no gradient text (`background-clip: text`), no hero-metric blocks, no identical icon+heading card grids, no decorative glassmorphism.
- **Don't** drift toward a **corporate dashboard** — no business-blue, no heavy chrome, no admin-panel data-table density for its own sake.
- **Don't** go **childish** — no mascots, cartoon illustration, or emoji as decoration. (Functional state/wayfinding emoji — 🌙 🎉 ✓ — are fine.)
- **Don't** use a `border-left`/`border-right` greater than 1px as a colored stripe on cards, findings, or bubbles. State reads as a full border + tint instead.
- **Don't** put a drop shadow on a resting surface. If it isn't floating (dock, modal, sticky bar), it's flat.
- **Don't** introduce a warm-tinted or cream background to add "warmth" — the corner glow and the violet are the warmth.
- **Don't** invent a fourth small font size or set body/buttons in mono for flavor.
