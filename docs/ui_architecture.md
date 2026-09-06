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

The landing is **two screens stacked**: a one-viewport hero, then `HowItWorks`
below the fold — the mechanism, the flowchart, the nine stages, the measured
numbers. That is why the landing is the one screen whose shell is `min-h-full`
rather than `h-full` (see §5): the page scrolls, which is also what makes the
header's scrolled-ground state work there.

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

## 3b · Frames, spacing, type — the minimalism pass

Three rules, each added because a count said so. All three live in `index.css`
next to the palette; the numbers below are what they replaced.

**One frame between a leaf and the page.** A frame is a border on three or more
sides. Before: every leaf in the landing explainer sat inside 2–4 of them (94 at
depth 2, 64 at 3, none below 2); Model had 36 at depth 2 and 6 at depth 3. After:
the explainer is 152 at depth 1 and none deeper, Model 308 at 1, the alert queue
1204 at 1 with a single control at 2. `Panel` enforces this itself — it publishes
a React context and a nested `Panel` collapses to `panel-sub`, which is the
weight that already existed for exactly this. Inside a frame, separate with a
background step and space.

Three things are **not** frames: single-edge accent rules (they carry a layer,
not a boundary), inline controls (a button's border is what makes it an object),
and `gap-px` separator grids. What *was* wrong, and is now fixed, is a border
sitting on top of a fill — `Tag`, `Bar`'s track, the ablation cards and the
counterfactual box each stated the same separation twice.

**Spacing is a scale.** `2 4 8 12 16 24 32 48` plus `gap-px`. 19 distinct values
before, most within 2px of a neighbour; 139 tokens rewritten.

**Six type sizes**, from ten. 78% of every use landed on the two smallest, so
hierarchy was carried almost entirely by weight and colour — the mirror image of
the mono monoculture this interface already fixed once. `xs` sat inside 2px of
both neighbours, `xl` had two uses and `4xl` had one. `md` 14→16 and `lg` 16→18
so prose and sub-headings are separated by something a reader can see.

**Colour simultaneity, not the palette.** The layer semantics are the product's
argument and are untouched. What changed is how many are painted at once: the
stage tour coloured all nine rows, putting five hues on screen and diluting the
system the footer key exists to teach. Only the selected row is coloured now, and
the footer key keeps its labels on the landing — where a reader first meets the
colours — and collapses to four `title`-bearing swatches everywhere after.

Two real contrast defects fell out of the sweep, both pre-existing:

- `text-white` on `--confirm`. Fine in light, where `--confirm` is a dark green;
  **2.11:1 in dark**, where it is a *light* green. `--surface` inverts with the
  theme: 5.00 light, 7.64 dark. There is no `text-white` left in the codebase.
- The alert queue's `·` and `—` separators are `text-rule` at 1.5:1 and were not
  marked as decoration, so a screen reader announced "middle dot" ~120 times down
  the queue and an audit counted 168 phantom failures. They are `aria-hidden`
  now, which is what they always were in intent.

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

The app shell is `h-full` **only while a run is scoring** — that screen owns its
own height. Everywhere else, including the landing, it is `min-h-full` and the
page scrolls: the alert queue is ~3,600px, and the landing is ~3,200px now that
`HowItWorks` sits under the hero. The hero holds one viewport with
`min-h-[calc(100svh-5rem)]` (the header above plus the status bar below).

---

## 6 · Components

| File | What it is |
|---|---|
| `App.tsx` | shell, header, routing, the two state flags |
| `StartScreen.tsx` | landing hero: dropzone, samples, veil over the field |
| `HowItWorks.tsx` | the explainer below the fold: flowchart, stage tour, results |
| `stages.ts` | the nine stages, in three registers — see below |
| `Processing.tsx` | scoring screen: counters, stage detail copy, timings |
| `StageTrack.tsx` | the serpentine progress track (lg+) |
| `Propagation.tsx` | the live diffusion field behind landing + scoring |
| `Sonar.tsx` | sweep companion on the scoring screen |
| `ThemeToggle.tsx` | three-state theme control |
| `ui.tsx` | shared primitives: `Panel`, `Stat`, `Bar`, `Counter`, `Tag`, `Chip`, `Eyebrow`, `drawOnMount` |
| `AlertQueue.tsx` | ranked queue, sorting, search, `j`/`k` navigation |
| `CaseFile.tsx` | one entity: evidence, SHAP, graph, attribution |
| `ModelPanel.tsx` | model transparency, ablation, both real-data validations |

### The explainer's ground, and why nothing is written on it

`HowItWorks` is **four opaque `--paper` plates on a live ground**, not one flat
slab. The ground is `--paper` at 55% over the fixed diffusion field, with the
`.plate-grid` hairline grid (40px minor, 200px major) painted on top of it, and
it shows in the 139px side gutters and the 32px between bands.

**Text never sits on the ground, and that is measured.** Both textures were tried
under body copy first:

| under body text | `--fusion` | `--ink-dim` | verdict |
|---|---|---|---|
| plain `--paper` | 4.71 | 4.95 | the floor |
| field through at 7% | **4.11** | **4.32** | fails AA |
| on a 200px grid line | **4.06** | **4.26** | fails AA |

Solving for the strongest grid line that still clears 4.55:1 against `--chain`
gives alpha **0.075** — a ground shift of 1.02:1, i.e. a grid nobody can see.
`--chain` and `--fusion` sit about 4% above the floor on paper and there is
nothing to spend it on. So the ground carries the texture and the plates carry
the words.

### Propagation — not decoration

**One canvas, `fixed inset-0 -z-10`, behind the whole landing** — hero and
explainer both, rather than a second instance under the explainer. Its pointer
handler is on `window` and maps through the canvas rect, so `fixed` costs it
nothing and the vantage point stays playable the entire way down the page.

It draws the product's own problem: a peer announces a transaction and the rest
relay after a **randomised per-peer delay**, which is the defence that makes
first-relay attribution wrong. **The pointer is a listening vantage point** —
peers within reach light up and report to it, which is the sensitivity curve from
the Model page made tangible.

**The field rolls as one travelling wave.** The per-node drift phase used to be
`n.phase` alone — a random constant — so every node bobbed on its own schedule
and 200 nodes read as static noise that happened to jitter. The phase now also
carries a term derived from the node's own position, so it advances across space
as well as time and the whole mesh rolls in one direction. Amplitude and
wavelength are both tuned to be *seen*: mean node spacing is `sqrt(DENSITY)` =
79px, so the original 7px sway was 9% of the gap — real in the numbers, invisible
on screen. 20px is a quarter of the spacing. A coherent wave tolerates that where
random jitter would not, because neighbours move almost together and the mesh
sways instead of tangling. Edges, dots, pulses and ripples all draw from
`n.x`/`n.y`, so none of them needs anything of its own.

**Wave speed follows the scroll**: `WAVE_HERO` 1.9× at the top easing to
`WAVE_CALM` 1.0× across the first screenful, because one canvas is fixed behind
the whole page and the hero wants a livelier field than the explainer, which sits
behind text people are reading. The phase is **accumulated** (`waveT += dt *
speed`) rather than derived from `now`: `sin(now / T)` with a changing `T` jumps
the instant `T` moves, and the whole field would snap mid-scroll.

**The veil must start where the field starts.** The field is `fixed` from y=0,
but the hero `<section>` begins below the 48px header, so a veil at `inset-0` of
that section left the field raw across the header band and veiled from the
heading down — a hard horizontal seam straight across the page at the header's
bottom edge. The veil is `-top-12`, and the section's `overflow-hidden` (which
used to clip the canvas when it lived inside, and now only clipped the veil) is
gone.

There is deliberately **no drawn boundary circle**. What a vantage point hears
falls away with distance; it does not stop at a line. A smoothstep falloff
carries it.

### HowItWorks, and the flowchart

Four bands: why first-seen attribution fails, an SVG flowchart of the two lanes
meeting at `FUSE`, an interactive tour of the nine stages, and four measured
figures each shown beside the baseline it has to beat.

Three things in the SVG are decisions, not accidents:

- **Everything in a lane sits on one vertical axis** — the trace, the lane label,
  the box, and the box's text. Box text was left-aligned under a centred label
  once, and that is exactly what reads as "misaligned".
- **One path per lane** is both the drawn connector and the `animateMotion` path
  for its packets. The boxes are filled `--surface` and painted over it, so the
  line simply disappears behind each box.
- **Prose does not go inside a viewBox.** A flowchart box has room for four
  words, and a reader who does not already know what "entity × IP co-occurrence"
  means is not helped by four words. **Pointing at any of the nine nodes opens a
  callout anchored to that node**, joined to it by a leader line in the node's
  own layer colour, explaining it in the register of `stages.ts` `PLAIN`. Hover
  and click both set it, so it works on touch.

`CALLOUT` holds each node's `edge` (the border the leader leaves from) and `x`
(the card's left edge) **in viewBox units**, so the HTML card and the SVG leader
agree without either measuring the other — the card is positioned in percentages
of the same box the viewBox maps onto.

**The card always overlaps the diagram, and that is forced.** Two 300-unit lane
boxes plus their margins consume the full 1000; there is no free column for a
300-unit card. So network cards open right and chain cards open left, each over
the far lane, for exactly as long as you point at something. This is why the card
is `pointer-events-none` — otherwise it steals the hover from the node it
describes, or from a node underneath, and the whole thing flickers.

Cards are vertically centred on their node, which keeps the leader a straight
horizontal line and means nothing has to measure the card's height. The two ends
are the exception: centred, the source card hangs 39px above the schematic and
the output card 42px below, putting a popover over the band's own heading. Those
two pin to `top: 0` / `bottom: 0` instead; the leader still leaves the node
horizontally, it just meets the card nearer a corner.

The callout layer is a `relative` wrapper **outside** the horizontal scroller.
Inside it, `overflow-x: auto` would compute `overflow-y` to `auto` as well and
turn any vertical overhang into a scrollbar. It is `hidden md:block`: below `md`
the schematic is narrower than its 680px min-width and scrolls, so a card
positioned in percentages would drift off its own node. That width gets a stacked
block underneath instead.

Hover fills a node with `--active-wash`, never with its own layer wash: the
stroke says which layer this is, the fill says you are pointing at it, and those
two jobs do not share a colour. Two contrast fixes came out of measuring the
hover state — the box sub-line steps `--ink-dim` → `--ink-soft` (4.22:1 in dark),
and the `FUSE` label goes to `--ink` (4.48:1 in light, two hundredths under).

The card is `aria-hidden` and pointer-driven; its nine explanations reach
assistive tech through an `sr-only` `<dl>` after the SVG instead. No tab stops
buried inside an SVG, and nothing is keyboard-only-inaccessible.

**The SVG's type is in viewBox units, so it is at the mercy of the render
width.** An earlier version put the card in a side column, which cut the
schematic to 814px (scale 0.814) and would have landed 13px type at 10.6px. Sizes
went up accordingly — heads 16, subs 13, mastheads 17, `FUSE` 18 — and every line
was checked with `getComputedTextLength()` against its box's inner width, not by
eye. As an overlay the card costs no width at all: the schematic is back to
1070px, scale 1.07.

**Packets need a NEGATIVE `begin`.** A positive delay leaves the circle parked at
`cx`/`cy` — the viewBox origin — as a coloured dot clipped into the top-left
corner until it fires. Measured: six of them at (-4,-4,5,5) for up to 3.2s. A
negative offset starts the animation already in progress instead.

`useArmed` starts the motion when the section scrolls into view — **and carries a
6-second fallback timer.** `IntersectionObserver` does not run while a document
is not being rendered: measured in a hidden browser pane, it never fired at all
and the diagram stayed permanently blank. Same guarantee `Counter` makes about
landing on its final value — the animation may be missed, the content may not.
For the same reason the results bars are not gated on `armed` at all: a figure
without its baseline is a claim.

### stages.ts — three registers of the same nine stages

`STAGES` (name + one line), `DETAIL` (the mechanism, for someone who knows what a
hypergeometric test is) and `PLAIN` (the first thirty seconds, before anyone has
agreed to care). `Processing` shows the first two while a run executes; the
landing shows `PLAIN` first and `DETAIL` under it, so nobody has to decide which
audience the page is for. One file, so the wait screen and the explainer cannot
drift apart.

The stage tour also carries a **layer colour per stage** — the same semantic
palette the footer key decodes, applied to the pipeline, so the run visibly
crosses from network to chain and back before anything is scored. It is not a
rainbow: `data` for the neutral stages, `network`, `chain`, `fusion` for model
output, `confirm` for the provenance write.

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

### Verified on the landing explainer

Measured at 1429×900 and at 375×812, both themes, with CSS transitions disabled
first (a frozen pane returns the *pre*-transition colour):

- 128 text nodes, **zero contrast failures** in light or dark, SVG text included.
- Zero horizontal page overflow at either width. The flowchart scrolls inside its
  own `overflow-x-auto` container below ~680px.
- Stage list and detail panel both measure 482px — the column is no longer half
  empty.
- One canvas on the landing, not two. 139px of live ground each side of the
  plates at 1429px, 16px at 375px.
- Zero contrast failures **with each flowchart node hovered**, both themes — SVG
  text checked against the shape it sits inside, at its rendered pixel size.
- Nine hittable nodes; hover and click both drive the card. `sr-only` resolves to
  a 1×1 clipped box, so the `<dl>` is not painting nine paragraphs on the page.
- All nine callouts checked: leader starts on the node's edge, ends on the card's
  near edge, sits at the node's vertical centre and lands inside the card's span;
  card inside the schematic horizontally, no vertical overhang (FUSE by 1px, a
  rounding artefact). Zero contrast failures with a callout open, both themes.

When measuring hover by dispatching `mouseover`, **await a tick before reading**.
React has not re-rendered on the same turn as the dispatch, and a synchronous
read returns the previous node's card for all nine rows — which looks exactly
like a card that never updates.

### Verified after the minimalism pass

Contrast, both themes, decoration excluded per WCAG: landing 123 checked,
alerts 1197, model 327, provenance 70, case file 88 — **zero failures on every
screen in both themes**. Zero horizontal overflow at 1429px and at 375px on
landing, alerts and model. `tsc -b` clean, `make offline-check` PASS, the
impeccable detector returns `[]`.

**`requestAnimationFrame` does not fire at all in a hidden pane** — measured:
zero frames in 45 seconds, and the tool call times out waiting. So the canvas
never paints a frame there, `getImageData` reads all-zero alpha, and no amount of
waiting produces a screenshot of the field. Anything about the field's *motion*
has to be judged on a real screen.

Known and accepted: at 375px the schematic scrolls inside its own container and
its sub-lines render at 8.8px. The card below carries the same words at full
size, and the demo target is a laptop.

Note the audit needs an alpha-aware background resolver: `#how` is a
`color-mix(... / 0.55)` over the fixed canvas over `body`, and a naive
`getComputedStyle().backgroundColor` read returns `color(srgb …)` which a plain
`rgb()` regex parses into near-black and reports false failures.

Not verified: **no screenshot was captured.** The browser pane was hidden for the
whole session, so every screenshot returned black and `document.visibilityState`
stayed `hidden`. Everything above is geometry and computed style, not pixels.

## 10 · Where this stands

The interface was rebuilt across `c8fcbec … 3ef619f`, then this document's §3b
(frames, spacing, type) and the landing explainer landed in `1b7b302`.
`git log --oneline c8fcbec~1..` is the narrative and every message states what
was measured.

Open, and deliberately not done:

- **Explanation faithfulness is unmeasured** — §9.
- **`ui/dist/` is committed** so a clone can `make serve` without a build step.
  Rebuild it with `make ui` and commit the result; do not re-add the ignore rule.
- The generator's `src_ip` is not reproducible across runs — a backend defect,
  recorded in `CLAUDE.md`, but it moves the attribution figures this interface
  displays, so a UI session should not be surprised by them shifting.

*Current at `1b7b302`.*
