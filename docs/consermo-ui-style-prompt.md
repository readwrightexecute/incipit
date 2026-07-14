# Restyle Incipit to the Consermo design language

You are working in the **incipit** repo — a FastAPI + Jinja2 + HTMX "mega-prompt wizard" that is server-rendered and has **no Node/frontend build step**. Your job is to restyle its UI to match the visual design language of a different product ("Consermo") described exhaustively below. You have no access to the Consermo codebase; **every design value you need is in this prompt**. You also cannot assume this description of incipit's file layout is exact — your working copy may have drifted from the one this prompt was written against — so **verify everything about the target repo yourself before changing it**.

## Step 0 — Survey the repo before touching anything (mandatory)

Build your own map of the frontend surface first:

1. Locate the templates directory (expected: `app/templates/` with a base layout plus step templates and a `partials/` folder) and the static assets directory (expected: `app/static/`).
2. Find where CSS currently lives. Expected: a vendored Pico CSS file (`pico.min.css`) plus a large `<style>` block inside the base template (`base.html`) that overrides Pico's `--pico-*` custom properties — but it may have been moved to a separate static stylesheet. Whatever you find is the ground truth.
3. Inventory the JS helpers (expected: `htmx.min.js`, an SSE extension, a `spinner.js` frame-based ASCII spinner engine, a `history.js`) and any self-hosted fonts (expected: a Departure Mono woff2 under `static/fonts/`).
4. List every template and partial and skim each one to understand what UI it renders. Expected surface (verify names; adapt if they differ):
   - a base layout with masthead, skip link, settings region, and global styles;
   - a step-1 idea form (large textarea, segmented radio-card project-type selector, repo-URL row, a fixed bottom action bar with a "Shoot the Moon" button);
   - a clarify step with numbered question inputs and `[ASSUMPTION]` fine print (e.g. `step3_clarify.html`, `partials/question_list.html`);
   - a sections/drafting step with an SSE-driven terminal-style status bar and per-section cards in pending/generating/error/done states, click-to-edit content, a refine input row, and example chips (e.g. `step4_sections.html`, `partials/section_card.html`, `section_editor.html`);
   - "party mode" round-table UI: a floating chat dock, chat bubbles (persona/facilitator/system), and approve/deny change cards (e.g. `partials/party_panel.html`, `party_chat.html`, `party_changes.html`, `party_change_card.html`, plus QA variants);
   - a final output view with a mono mega-prompt block and Copy / Download / New session actions (e.g. `step6_final.html`);
   - auxiliary views: moonshot progress, session resume, expired session, settings panel with model/endpoint/API-key fields.
5. Note the current theme. Expected: a hard-pinned dark violet "Tokyo Night"-style theme (`data-theme="dark"` on `<html>`, violet `#bb9af7`-family primaries, a radial glow body background, a rainbow-hue spinner). Whatever the current palette is, it gets replaced wholesale by the token system below.

Only after this survey, plan your edits against what actually exists.

## Hard constraints (hold regardless of file names)

- **No Node/Tailwind/PostCSS build pipeline.** Implement with plain CSS custom properties. If the repo overrides Pico CSS variables today, prefer keeping Pico and re-pointing its `--pico-*` tokens at the new palette plus a custom app layer (the pattern the repo likely already proves out); replacing Pico with a small hand-written stylesheet is acceptable if it fights you.
- Keep all HTMX behavior, SSE wiring, element IDs, `hx-*` attributes, form field names, and JS hooks exactly as they are — templates get swapped in as fragments, so styles must be global (base template or a static CSS file), never per-partial.
- Preserve existing accessibility features wherever you find them: skip link, `aria-live` regions, `prefers-reduced-motion` handling, enlarged touch targets on coarse pointers. This is a reskin, not a refactor.

## The aesthetic in one paragraph (guides everything you improvise)

Consermo is **calm, restrained enterprise SaaS blended with an AI-builder workspace**: clear, precise, confident, quiet. Nearly monochrome neutral surfaces; flat cards separated by 1px borders, **no shadow drama**; a single trusted-action blue for primary actions; teal reserved as a "you are working here" marker; amber means "look at this soon," never panic; red **only** for errors/destructive/blocked. Explicitly banned: decorative gradients, novelty AI purples, glow effects, rainbow color cycling, red-as-generic-warning. Status is always icon/text + color, never color-only. Loading states are calm muted sentences ("Drafting…"), not flashy animation. Monospace is for technical artifacts (IDs, paths, code, the generated prompt), never ordinary body copy. **If the repo still has the violet "Tokyo Night + glow" dark theme, that is the exact opposite of this — remove the radial glow background, the violet palette, and any rainbow spinner colors entirely.**

## 1. Color tokens

Define as CSS custom properties. Consermo is light-mode default with a class-toggled dark mode; implement both (see §7). Every value below is verbatim from the source.

### Light theme (`:root`, `color-scheme: light`)

| Token | Value | Role |
|---|---|---|
| `--background` | `#FFFFFF` | page background |
| `--foreground` | `#0A0A0A` | primary text |
| `--card` | `#FFFFFF` | card/panel surface (flat, border-separated) |
| `--card-foreground` | `#0A0A0A` | text on cards |
| `--popover` | `#FFFFFF` | dropdowns/menus/docks |
| `--primary` | `#2563EB` | trusted-action blue: primary buttons, links, active nav, brand mark |
| `--primary-foreground` | `#FFFFFF` | text on primary |
| `--secondary` | `#F5F5F5` | secondary button fill |
| `--secondary-foreground` | `#171717` | text on secondary |
| `--muted` | `#F5F5F5` | hover washes, tab-list track, subtle fills |
| `--muted-foreground` | `#737373` | secondary/meta text, placeholders |
| `--accent` | `#14B8A6` | builder teal — ONLY for "active/current step" markers |
| `--accent-foreground` | `#042F2E` | text on accent |
| `--attention` | `#F59E0B` | amber — needs review soon (non-blocking warnings) |
| `--attention-foreground` | `#3B2502` | text on attention |
| `--safe` | `#10B981` | green — success/done/healthy |
| `--safe-foreground` | `#042F2E` | text on safe |
| `--blocked` / `--destructive` | `#DC2626` | red — errors, destructive, failed only |
| `--blocked-foreground` | `#FFFFFF` | text on blocked |
| `--border` | `#E5E5E5` | all borders/dividers |
| `--input` | `#E5E5E5` | input borders |
| `--ring` | `#A3A3A3` | focus ring color |

### Dark theme (`.dark` class or `[data-theme=dark]`, `color-scheme: dark`)

| Token | Value |
|---|---|
| `--background` | `#0A0A0A` |
| `--foreground` | `#FAFAFA` |
| `--card` / `--popover` | `#171717` |
| `--card-foreground` | `#FAFAFA` |
| `--primary` | `#60A5FA` |
| `--primary-foreground` | `#08111F` |
| `--secondary` / `--muted` | `#262626` |
| `--secondary-foreground` | `#FAFAFA` |
| `--muted-foreground` | `#A3A3A3` |
| `--accent` | `#5EEAD4` (foreground `#042F2E`) |
| `--attention` | `#FBBF24` (foreground `#2A1A00`) |
| `--safe` | `#10B981` (foreground `#042F2E`) — no dark variant by design |
| `--blocked` / `--destructive` | `#DC2626` (foreground `#FFFFFF`) — no dark variant |
| `--border` / `--input` | `#262626` |
| `--ring` | `#737373` |

If the repo defines its own semantic status variables (likely `--danger`, `--warning`, `--success`, `--info`), remap them: danger→blocked, warning→attention, success→safe, info→primary. Alpha tints are used a lot; with hex tokens use `color-mix(in srgb, var(--primary) 10%, transparent)` or keep RGB-triplet companion variables (a `rgb(var(--accent-rgb) / .12)` pattern may already exist in the base styles — reuse it).

## 2. Typography

- **Families**: sans = **Geist** (`'Geist Variable', 'Geist Sans', ui-sans-serif, system-ui, sans-serif`), mono = **Geist Mono** (`'Geist Mono Variable', 'Geist Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace`). Consermo self-hosts both (no CDN at runtime). Do the same: download the variable woff2 files into the repo's static fonts directory —
  - `https://cdn.jsdelivr.net/npm/@fontsource-variable/geist@5.2.9/files/geist-latin-wght-normal.woff2`
  - `https://cdn.jsdelivr.net/npm/@fontsource-variable/geist-mono@5.2.8/files/geist-mono-latin-wght-normal.woff2`

  and declare:

  ```css
  @font-face {
    font-family: "Geist Variable";
    src: url("/static/fonts/geist-latin-wght-normal.woff2") format("woff2");
    font-weight: 100 900; font-style: normal; font-display: swap;
  }
  @font-face {
    font-family: "Geist Mono Variable";
    src: url("/static/fonts/geist-mono-latin-wght-normal.woff2") format("woff2");
    font-weight: 100 900; font-style: normal; font-display: swap;
  }
  ```

  (Adjust the URL path prefix to however static files are actually served — verify in the survey.) If a Departure Mono font is present, **remove/replace it**; Geist Mono takes over all mono duties, including any terminal-style blocks.
- **Type scale** (Consermo is a dense, small-type UI — body copy runs at 14px, not 16px):
  - **Display** (page hero/headline, e.g. the step-1 masthead): `34px`, weight `650`, line-height `1.12`, letter-spacing `-0.03em`.
  - **Display-sm** (page/section titles): `24px`, weight `650`, line-height `1.18`, letter-spacing `-0.02em`.
  - **Card/panel titles**: `16px`, weight `600` (semibold), foreground color.
  - **Body / controls / labels**: `14px` / line-height `20px`, weight `400`; labels and buttons weight `500` (medium).
  - **Meta / hints / fine print**: `12px` / line-height `16px`, `--muted-foreground`.
  - **Big numbers** (if any metric-like values): `24px`, semibold, `font-variant-numeric: tabular-nums`.
  - **Mono role** (IDs, code, the generated mega-prompt, terminal output): Geist Mono `13px`, weight `400`, line-height `1.45`.
- Antialiased rendering (`-webkit-font-smoothing: antialiased`).

## 3. Shape, spacing, borders, shadows

- **Radii scale** (used strictly by size class): `6px` inputs/badges/compact controls · `8px` buttons/tabs/nav items · `12px` cards/panels · `16px` major dialogs/empty states · `999px` **only** for status pills and compact filter chips.
- **Spacing anchors**: page gutter `24px` (16px on mobile), gap between major page sections `20px`, dense row vertical padding `10px`, card internal padding `16px` (dialogs `24px`), gaps mostly `8px`/`12px`.
- **Borders**: everything structural is `1px solid var(--border)`. Cards are **flat**: border, no shadow.
- **Shadows** (the only two): inputs get a whisper `0 1px 2px 0 rgb(0 0 0 / 0.05)`; overlays (dialogs, floating docks) get `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`. Nothing else. No inset glows.
- **Focus (critical, applied to every interactive element)**: `outline: none;` then on `:focus-visible` — border-color becomes `var(--ring)` **and** a 3px soft ring: `box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 50%, transparent)`.
- **Disabled**: `opacity: .5; pointer-events: none;`.

## 4. Component recipes (concrete CSS)

Match these to whatever elements/classes exist after your survey; class names below are the *expected* incipit ones.

**Buttons** — base: inline-flex, centered, gap `8px`, height `36px`, padding `8px 16px`, radius `8px`, font `14px`/weight `500`, `transition: color .15s, background-color .15s, border-color .15s` (easing `cubic-bezier(0.4, 0, 0.2, 1)`), focus ring per §3. Small: `32px` high, padding-x `12px`. Large: `40px` high, padding-x `24px`.
- *Primary*: `background: var(--primary); color: var(--primary-foreground);` hover = same color at 90% opacity (`color-mix(in srgb, var(--primary) 90%, transparent)`).
- *Secondary*: `background: var(--secondary); color: var(--secondary-foreground);` hover at 80% opacity.
- *Outline*: `border: 1px solid var(--border); background: var(--background);` hover `background: var(--muted)`.
- *Ghost*: transparent; hover `background: var(--muted)`.
- *Destructive*: `background: var(--destructive); color: #fff;` hover 90%.
- *Link-style*: `color: var(--primary); text-underline-offset: 4px;` underline on hover only.
- If the repo uses Pico's button classes, map them: default button → primary; `.secondary` → secondary; `.secondary.outline` / `.contrast.outline` → outline; `.contrast` (likely "Shoot the Moon" / party buttons) → outline or secondary — **not** a second saturated color.

**Inputs / textareas / selects** — height `36px` (textarea `min-height: 6rem`; if the idea textarea has a larger min-height like `10rem`, keep it), radius `6px`, `border: 1px solid var(--input)`, `background: var(--background)`, padding `4px 12px` (textarea `8px 12px`), font `14px`, `color: var(--foreground)`, placeholder `var(--muted-foreground)`, shadow-xs from §3, focus ring per §3. Invalid/error: `border-color: var(--blocked)` + ring `color-mix(in srgb, var(--blocked) 20%, transparent)`.

**Cards / panels** (section cards, settings panel, history items — likely `article` elements and a `.section-content` block): `background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px;` internal column gap `16px`. Header = title (16px semibold) + optional description (14px `--muted-foreground`). Interactive/clickable cards hover to `background: color-mix(in srgb, var(--muted) 50%, transparent)`. A card that **needs attention** switches only its border to `var(--attention)` (never a full amber wash).

**Badges / pills** (status chips, "Queued", applied/denied states, count bubbles): `border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 600;` variants — review/warn: `background: var(--attention); color: var(--attention-foreground)`; success/done: `background: var(--safe); color: var(--safe-foreground)`; error/blocked: `background: var(--blocked); color: #fff`; neutral: `background: var(--muted); color: var(--muted-foreground)`. Always contains a text label, never color alone.

**Small chips** (refine-example chips, likely `.ex-chip`): keep pill shape, `12px` text, `1px solid var(--border)`, `color: var(--muted-foreground)`; hover: `border-color: var(--primary); color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, transparent)`.

**Segmented selectors** (radio-card project-type picker, likely `.seg-btn`): `border: 1px solid var(--input); border-radius: 8px; background: var(--background)`; hover `border-color: var(--ring)`; **checked** = the "active builder context" treatment: `border-color: var(--primary); background: color-mix(in srgb, var(--primary) 10%, transparent)` with an inset `box-shadow: inset 0 0 0 1px var(--primary)`; focus-visible ring per §3.

**Nav/header**: top bar `56px` high, `border-bottom: 1px solid var(--border)`, padding-x = page gutter, `background: var(--background)`. Brand mark = a `20px` square with `border-radius: 6px; background: var(--primary)` next to the wordmark at `14px` weight `600`. Active-nav treatment (reuse for a current-step indicator if you add one): `background: color-mix(in srgb, var(--primary) 10%, transparent); color: var(--primary); border-radius: 8px; padding: 8px 12px; font: 14px/1 medium`. Idle items: `color: var(--muted-foreground)`, hover `background: var(--muted); color: var(--foreground)`.

**Modals** (settings panel, any history modal): overlay `rgba(0,0,0,.5)`; content `max-width: 512px`, `border-radius: 16px`, `border: 1px solid var(--border)`, `background: var(--background)`, `padding: 24px`, overlay shadow from §3; title 16px semibold, description 14px muted; footer buttons right-aligned with `8px` gap; close button = top-right icon at `opacity: .7`, hover `1`. Enter animation: fade + scale from `0.95` over `200ms`.

**Tables/lists** (e.g. a session-history list): header cells 14px medium `--muted-foreground`, `40px` tall; body rows separated by `border-bottom: 1px solid var(--border)`, cell padding `10px 8px`, hover wash `color-mix(in srgb, var(--muted) 50%, transparent)`.

**Collapsible/disclosure** (party dock, any accordion): bordered `12px`-radius box; trigger row `padding: 12px 16px`, 14px medium, chevron `▾` in `--muted-foreground` that rotates 180° with `transition: transform .15s` (`transition: none` under reduced motion); open content separated by `border-top: 1px solid var(--border)`, padding 16px.

**Links** in prose: `color: var(--primary)`, no underline at rest, underline on hover, `text-underline-offset: 4px`.

**Loading/progress**: Consermo's loading language is a calm muted sentence — `14px`, `--muted-foreground`, `aria-live="polite"`, e.g. "Drafting…". If the repo has a frame-based ASCII spinner engine (likely `spinner.js` driving `.spinner` spans, possibly with rainbow hue cycling), keep the mechanism and SSE heartbeat but **kill the rainbow**: fix spinners to a single color (`--muted-foreground`, or `--primary` for the primary in-flight card) — via a `data-color="off"`-style opt-out if the engine supports one, or by overriding the engine — and prefer quiet frame sets (braille pulse or a sweep bar) over louder ones.

**Code / generated output** (section content blocks, the final mega-prompt, terminal/status blocks): Geist Mono `13px/1.45`, `background: var(--muted)` (or `--card` in dark), `border: 1px solid var(--border)`, `border-radius: 8px`, padding `8px 12px`, `white-space: pre-wrap`. If a terminal-style status bar exists (likely `#status-bar`/`.terminal` with a `❯` prompt glyph and blinking `▋` cursor), it may keep the prompt glyph (colored `var(--primary)`) and cursor, but drop any near-black custom background and inset glow — restyle it as this standard mono block.

## 5. Layout

- **Page shell**: single centered column (this app is a wizard, not a sidebar app). Content `max-width: 672px` for forms/text-heavy steps and up to `768px–896px` for the sections/final views; page gutter `24px` (16px under 640px). Add a slim `56px` bordered top header per §4 (brand mark left, settings + theme toggle right) replacing any inline settings link; if the base template compresses the masthead after step 1 (a `:has()` rule keying off a step marker), preserve that behavior.
- **Fixed bottom action bar** (if present — likely `.action-bar`): keep the mechanics (fixed, z-index, multi-zone flex, mobile wrap); restyle as `background: color-mix(in srgb, var(--background) 92%, transparent); backdrop-filter: blur(6px); border-top: 1px solid var(--border);` padding `10px 16px`.
- **Floating party dock** (if present — likely `.party-dock`): a popover surface — `background: var(--popover); border: 1px solid var(--border); border-radius: 12px;` overlay shadow from §3. Dock header: **neutral** (`background: var(--popover)`, bottom border, 14px semibold title) — not a colored banner. Chat bubbles: assistant/persona = `background: var(--muted); border: 1px solid var(--border); border-radius: 10px;` facilitator = primary-tinted (`color-mix(in srgb, var(--primary) 8%, var(--card))` bg, primary-tinted border); system = transparent + dashed border, 12–14px muted, centered. Speaker names 14px semibold; the facilitator name may use `--attention`.
- **Change cards** (party proposals with applied/denied states, if present): state = border + faint tint on the whole card, re-pointed at the new tokens: applied → `border-color: color-mix(in srgb, var(--safe) 50%, var(--border)); background: color-mix(in srgb, var(--safe) 8%, var(--card))`; denied → `opacity: .55` + `border-color: color-mix(in srgb, var(--blocked) 45%, var(--border))`.
- **Responsive**: breakpoints at `640/768/1024px`; if existing media queries sit at odd widths (600/700px), move them to 640/768. Mobile keeps single column; preserve any coarse-pointer touch-target rules you find.

## 6. Motion

Minimal and functional: `transition: color/background-color/border-color .15s cubic-bezier(0.4, 0, 0.2, 1)` on interactive elements; modal enter = fade + scale `0.95→1` over `200ms`; slide-in panels (if any) `300ms` close / `500ms` open ease-in-out; chevron rotate `.15s`. If chat bubbles have a small entrance animation (~250ms fade + 4px rise), keep it — it fits. Preserve and extend any `prefers-reduced-motion` block (no loops, no entrances, spinner holds one frame).

## 7. Theme handling

Support **light and dark** with system-preference default (the repo is likely hard-pinned to dark via `data-theme="dark"` on `<html>` — change that):
- Pre-paint inline script in `<head>` (before CSS applies): read `localStorage.getItem('incipit-theme')`; resolve to dark if stored `"dark"`, or if stored ≠ `"light"` and `matchMedia('(prefers-color-scheme: dark)')` matches; set the theme attribute/class on `<html>` accordingly (no flash of wrong theme). Wrap storage access in try/catch.
- Set `color-scheme: light` / `dark` on the respective token blocks.
- Add a theme toggle in the header: an **outline small button** labeled with the current preference ("Theme: System" / "Theme: Dark" / "Theme: Light") that cycles system → dark → light and persists to localStorage, with an `aria-label` describing the switch.

## 8. Acceptance checklist

- [ ] Repo surveyed first; all styling changes target the files that actually exist in this working copy.
- [ ] No violet/purple anywhere; no radial glow background; no rainbow spinner hues; no gradients.
- [ ] Both light and dark themes work, default to system preference, persist, no first-paint flash.
- [ ] Geist / Geist Mono self-hosted from the static fonts directory and used everywhere (any Departure Mono removed); body UI reads at 14px, meta at 12px, mono at 13px.
- [ ] Every interactive element shows the 3px `--ring` focus treatment on `:focus-visible`.
- [ ] Cards are flat 1px-bordered surfaces at 12px radius; buttons 8px; inputs/badges 6px; dialogs 16px; pills only for status chips.
- [ ] Red appears only on errors/destructive actions; amber for "review" states; green for done/applied; teal (if used at all) only marks the active step/context.
- [ ] All HTMX/SSE flows (question polling, section drafting cards, party dock, refine, settings, final copy/download — whatever exists here) still function; reduced-motion and touch-target rules preserved.
