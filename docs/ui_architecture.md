# UI architecture

What the interface is, how it is put together, and the traps that cost real time
to find. Everything here is current as of the commits listed at the bottom.

Backend, model and evaluation live in the other docs; this file does not repeat
them. See `docs/technical_writeup.md` and `CLAUDE.md`.

---

## 1 · Screen flow

Upload-first. The app opens on a start screen even when a previous run is
persisted in `data/case.duckdb`, because scoring a capture is the thing the
product does and landing inside someone else's old results is not a demo.

```
StartScreen ──drop file / pick sample──▶ Processing ──done──▶ AlertQueue
     ▲                                                             │
     └──────────────── click the BTC·Fusion wordmark ──────────────┘
```

**Two independent state flags in `App.tsx`, and they are not the same thing.**
Collapsing them was a real bug — opening Model silently revealed a run the user
had never loaded.

| flag | means | set by |
|---|---|---|
| `entered` | left the landing | opening Model; starting a run; "view last run" |
| `runReady` | a run exists **that the user asked for this session** | a completed run; "view last run" |

- `Model` needs neither — it reads artefact files and works with no run at all.
- `Alerts`, `Provenance` and the header's run summary need `runReady`.
- The guard is on **what renders**, not only what is clickable: a hand-typed
  `#/alerts` falls back to the landing. Hiding a nav button is not a guarantee.
- The wordmark clears both. It is disabled during a run.

`showingStart` is one expression driving both the shell height and the body, so
the two can never disagree about which screen is up.

---

## 2 · Type

Three faces, all self-hosted via `@fontsource` so the air-gap holds.

| Role | Face | Tailwind |
|---|---|---|
| Display / headings | **Archivo** 700–800 | `font-cond` |
| UI and prose | **Public Sans** | default `font-sans` |
| Values and identifiers | **Spline Sans Mono** | `.mono` |

**IBM Plex was removed on purpose.** Plex Sans over Plex Mono has become the
default "technical product" pairing, so it now signals template rather than
instrument. Public Sans is the US Web Design System face — drawn for government
interfaces, which is an argument this project can actually make.

**The rule that matters: mono is for values only.** txid, entity id, IP, ASN,
figures, timestamps. Labels, headings, chips and prose are Public Sans. An
identifier only pops out of a dense row if the words around it are set in
something else. The alert queue was once 606 of 606 text nodes in mono inside a
1.33× size range, which is precisely why it read as a printed table.

Two utilities in `index.css` carry the hierarchy:

- `.display` — the one masthead per screen, `clamp(22px, 2.9vw, 32px)`
- `.figure` — the headline number a screen is about
- `.eyebrow` — section label (Public Sans, **not** mono)
- `.colhead` — table column label. Deliberately distinct from `.eyebrow`: a
  section heading and a column label must not be the same visual object.

---

## 3 · Colour

The layer palette is **semantic, not decorative**. A colour is a claim about
provenance.

| Token | Means |
|---|---|
| `--chain` | blockchain-layer facts — addresses, tx counts, BTC values |
| `--network` | network-layer facts — IPs, ASNs, novelty |
| `--fusion` | model output and confidence |
| `--confirm` | analyst actions, passing gates |
| `--danger` | failures |
| `--data` | neutral / absent |

**`--active` / `--active-wash` are interaction, not provenance.** Before they
existed, `--fusion` was doing five jobs at once — layer semantic, nav underline,
row hover, active chip, slider thumb — so orange could mean "model output" or
"you are pointing at this". A semantic colour that also marks focus has stopped
being semantic.

**Contrast floors are load-bearing.** `--ink-dim` was `#6F808D` = 4.08:1 on white
across 338 nodes of the landing screen, and tag text was 3.36:1. Both failed AA at
the size they were used. They are now 5.50:1 and 5.24:1. Do not lighten them.

There is a colour key in the footer, because the semantic system previously
existed only in a CSS comment and no viewer could decode it.

---

## 4 · Theme

Three states — `system` (default), `light`, `dark` — in `ThemeToggle.tsx`,
persisted to `localStorage` under `btcfusion.theme` and applied as
`<html data-theme>`.

- An inline script in `ui/index.html` reads the same key **before first paint**.
  Without it a dark-preference machine gets a white flash on every load.
- Dark is not an inversion. Surfaces step **up** from an almost-black ground, and
  the layer colours are re-picked, because `#2D6A9F` chain-blue on a near-black
  panel measures 2.1:1 and is unreadable.
- `--chrome` exists because the header used to be `bg-ink`, and `--ink` is the
  *text* colour — it inverts with the theme, so the bar would have flipped to a
  light slab. Chrome is dark in both themes.

---

## 5 · Layout

**The header is the page, not a bar on it.** Transparent with a single hairline,
so on the landing the diffusion field runs straight through it. It takes a
`bg-surface` ground only once `window.scrollY > 4`, because a transparent bar
over scrolling text is unreadable.

**There is no `load capture` control anywhere.** Ingest is the landing's job
alone; a second upload control in the chrome was a way to bypass the flow.

### The height trap, which cost the most time

`main` is `flex-1`, so its **specified** height is `auto` even though its used
height is correct. A child's `h-full` therefore has nothing to resolve against
and collapses to content height. This bit twice in one screen: the landing
measured 498px inside a 645px main, and its scroller measured 578px inside 345px.

**Rule: in a flex column, stretch children with `flex-1 min-h-0`, never `h-full`.**

The app shell is `h-full` on the landing and processing screens (they own their
own scrolling) and `min-h-full` everywhere else (the alert queue is ~3,600px and
the page must scroll).

---

## 6 · Components

| File | What it is |
|---|---|
| `App.tsx` | shell, header, routing, the two state flags |
| `StartScreen.tsx` | landing: dropzone, samples, veil over the field |
| `Processing.tsx` | scoring screen: counters, stage detail copy, timings |
| `StageTrack.tsx` | the serpentine progress track (lg+) |
| `Propagation.tsx` | the live diffusion field behind landing + scoring |
| `Sonar.tsx` | sweep companion on the scoring screen |
| `ThemeToggle.tsx` | three-state theme control |
| `ui.tsx` | shared primitives: `Panel`, `Stat`, `Bar`, `Counter`, `Tag`, `Chip`, `Eyebrow`, `drawOnMount` |
| `AlertQueue.tsx` | ranked queue, sorting, search, `j`/`k` navigation |
| `CaseFile.tsx` | one entity: evidence, SHAP, graph, attribution |
| `ModelPanel.tsx` | model transparency, ablation, both real-data validations |

### Propagation — not decoration

It draws the product's own problem: a peer announces a transaction and the rest
relay after a **randomised per-peer delay**, which is the defence that makes
first-relay attribution wrong. **The pointer is a listening vantage point** —
peers within reach light up and report to it, which is the sensitivity curve from
the Model page made tangible.

There is deliberately **no drawn boundary circle**. What a vantage point hears
falls away with distance; it does not stop at a line. A smoothstep falloff
carries it.

### StageTrack

Boustrophedon path — left→right, turn, right→left, turn, left→right. Progress is
a **second copy of the same path** revealed by `stroke-dashoffset`, so the fill
follows the curve through both turns; one CSS transition drives it. Node centres
come from `getPointAtLength()` on the real path, so a node cannot drift off the
line. Five packets travel the completed run, wrapping within it — the fill says
how far, the packets say it is still moving.

Below `lg` this falls back to a vertical rail: nine labelled nodes across three
rows at 375px is unreadable.

---

## 7 · Motion

One idea: **instrumentation coming alive.** A trace draws, a bar grows, a counter
settles. 150–900ms, exponential ease-out (`cubic-bezier(.16,1,.3,1)`), no bounce,
no fade-up-on-scroll. Utilities: `.anim-rise`, `.anim-bar`, `.anim-draw`,
`.animate-ping-soft`.

`prefers-reduced-motion` neutralises the **initial** states too, not just the
durations — otherwise `animation-fill-mode: both` strands elements at their 0%
keyframe: an invisible row, a zero-width bar, an undrawn curve. Reduced motion
must mean no motion, never no content.

**Time-based, never per-frame.** `n.lit *= 0.988` per frame runs at a different
speed on a 120Hz display than a 60Hz one. Use `dt`.

**Any animated number must be guaranteed to land.** `requestAnimationFrame` is
suspended while a tab is hidden, so a counter started before a tab switch strands
partway — observed live at `0.004` for a metric whose real value is `0.0245`. A
number frozen at 15% of the truth is not cosmetic in a forensics tool. `Counter`
carries a `setTimeout` that force-sets the final value.

---

## 8 · Verifying UI work

```bash
cd ui && npx tsc -b --force      # the REAL typecheck
cd ui && npm run build           # runs tsc -b, then bundles
node ~/.claude/skills/impeccable/scripts/detect.mjs --json \
  ui/src/App.tsx ui/src/ui.tsx ui/src/ThemeToggle.tsx ui/src/components
make offline-check               # no URLs in application code
```

**`npx tsc --noEmit` validates NOTHING here.** The root `tsconfig.json` is
`"files": []` with project references only, so it exits 0 on a codebase with real
errors. It did exactly that for a while. Always `tsc -b`.

`@fontsource` imports are local packages, not URLs, so `offline-check` still
passes with three self-hosted families.

### Browser-pane traps when verifying

These are testing artefacts, not product bugs. Recognise them rather than
"fixing" the wrong layer.

- **The pane collapses.** `clientWidth` reads 0 and every element appears to
  overflow with absurd heights. Force a paint with a screenshot in the same
  `browser_batch` before measuring.
- **rAF is suspended while the pane is hidden**, so canvas animations freeze and
  `window.scrollTo` may not dispatch a scroll event. Batch the screenshot and the
  measurement together.
- **Compressed screenshots flatten soft gradients.** Sample canvas pixels with
  `getImageData` instead of judging by eye.
- **CSS transitions race the read.** A background measured immediately after a
  class flips returns the pre-transition value. Wait past the duration.

---

## 9 · Known open items

- **Explanation faithfulness is not measured.** SHAP reasons are shown but no
  deletion/insertion test proves the highlighted features drive the prediction.
  This is the one item from the original plan never built.
- The `stress` generator profile has never been run and would likely OOM.
- Scaling is superlinear: 4.4× the data cost 8.9× the time.

---

*Current at `3ef619f`. The UI was rebuilt across commits `c8fcbec … 3ef619f`;
`git log --oneline c8fcbec~1..` is the narrative, and each message states what
was measured.*
