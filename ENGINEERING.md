# ENGINEERING.md — working notes for this repo

SIH 2026 · PS 26146 (NTRO) · correlating Bitcoin **network-layer** traffic with
**blockchain-layer** activity to produce ranked, explainable leads, fully offline.

## Read these before proposing anything

Do not re-derive what is already written down, and do not duplicate it into new files.

| File | What it settles |
|---|---|
| `docs/technical_writeup.md` | approach, model choice, evaluation, limitations |
| `docs/ps_compliance.md` | every PS requirement → the command that verifies it |
| `docs/external_validation.md` | the three validation tracks and what each does NOT prove |
| `docs/attribution_method.md` | the statistics behind network↔chain attribution |
| `docs/generator_parameters.md` | every synthetic-data parameter and its justification |
| `docs/model_card.md` | intended use, failure modes |
| `docs/ui_architecture.md` | **the interface**: screen flow, type, colour, theme, motion, and the traps |

## Environment — the things that waste a turn if you get them wrong

- **Work from `btc-fusion/`**, not the parent `sih26/`. Paths in every command assume it.
- Python is **`.venv/bin/python`**. Never system `python3`.
- Ad-hoc scripts need **`PYTHONPATH=.`** — the package is installed editable but scripts
  run outside it.
- **`npx tsc --noEmit` in `ui/` validates NOTHING.** The root tsconfig is `"files": []`
  with project references only, so it exits 0 on real errors. Always **`npx tsc -b`**
  (which is what `npm run build` runs).
- Docker on Apple Silicon **must** pass `--platform linux/amd64`; the vendored wheels are
  manylinux x86_64 and an unpinned build dies at the pip step. Already set in the Makefile.
- **Never commit `data/external/**/*.csv`** (1.3 GB, and not ours to redistribute). The
  Elliptic + Elliptic++ sets live there and only `make validate-external` /
  `make validate-elliptic-pp` read them. Their *results* are committed as
  `artifacts/v1/{external,elliptic_pp}_validation.json`.
- **`ui/dist/` IS committed, on purpose.** `make serve` serves that bundle, and a clone
  without it shows a blank page — this bit a teammate. `ui/.gitignore` no longer excludes
  it; do not put the rule back. Rebuild with `make ui` and commit the result.
- **`uv` is required** by `make setup`. A teammate without it gets
  `uv: No such file or directory` on the very first step. Install and PATH instructions
  are the first block of the README.
- **Sample captures are generated, never committed.** `capture.csv` is 230 MB and
  `bulk.csv` ~1 GB, both past GitHub's 100 MB per-file limit. `make bootstrap` makes them.

## Rules this codebase enforces on itself

- **`make offline-check` greps `btcfusion/` for `https?://` and fails.** It cannot tell a
  citation from an endpoint. Put URLs in docs, never in application code.
- **The leak test gates everything.** If `make verify-all` reports a strict lift above
  1.30×, the generator encodes its own labels and every downstream number is void. Expect
  third-decimal drift between runs — that is OpenMP float reduction order, not a defect.
- **Reproducibility is now a property, not a claim — and three separate bugs had to
  die for it.** `make reproduce` produces byte-identical output and identical metrics.
  (1) `generator/network.py` picked an actor's announcing IP with Python's randomised
  `hash()`, so `src_ip` differed between runs; it uses `zlib.crc32` now. (2)
  `eval/labels.py` resolved an ambiguous cluster's ground-truth label with
  `sort().group_by().first()` — polars guarantees neither ordering — so **the labels
  themselves moved between runs** (`n_positive` on the train fold went 3738 → 3729) and
  every metric graded against them moved too; ties now break on the true entity id.
  (3) `transaction_feature_matrix` returned rows in join order while the transaction
  head holds out a validation fraction *as ordered*; it sorts by txid now. Verified:
  two consecutive `train` runs differ in **zero** metric keys, where they used to differ
  in 186. `tests/test_determinism.py` guards all three. **Do not reintroduce a bare
  `hash()`, an unordered `group_by().first()`, or an unsorted matrix handed to a model.**

- **Degrade, never fail.** If a stage raises, the run continues and the UI says
  "unavailable". A stack trace in front of an analyst is the one unacceptable outcome.
- **Every published number must trace to an artefact file.** If a figure is not produced by
  `make reproduce`, it does not go in a doc.

## UI rules that are load-bearing

Full reasoning in `docs/ui_architecture.md`; these are the ones that break things.

- **Mono is for values only** — txid, IP, ASN, figures. Labels and prose are Public Sans.
  Mono everywhere is what made the queue read as a printed table.
- **`--fusion` means model output, nothing else.** Interaction uses `--active`. A semantic
  colour that also marks hover has stopped being semantic.
- **Do not lighten `--ink-dim` or `--fusion`.** They sit at 5.50:1 and 5.24:1; their
  previous values failed WCAG AA at the size they are used.
- **In a flex column, stretch with `flex-1 min-h-0`, never `h-full`.** `main` is `flex-1`,
  so its specified height is `auto` and a percentage height resolves against nothing.
- **`entered` and `runReady` are different flags.** Model needs neither; Alerts and
  Provenance need `runReady`. Merging them leaks a run the user never loaded.
- **Any animated number needs a guaranteed final value.** rAF is suspended in a hidden
  tab; a counter can otherwise strand at 15% of the truth and display a false figure.
- **One frame between a leaf and the page.** A frame is a border on 3+ sides. `Panel`
  enforces this through React context — a nested `Panel` collapses to `panel-sub`. Inside
  a frame, separate with a background step and space, never another border, and never a
  border on top of a fill. Single-edge accent rules and inline controls are not frames.
- **Spacing is a scale: `2 4 8 12 16 24 32 48`** (plus `gap-px` where a 1px gap draws a
  rule). There were 19 ad-hoc values before; do not reintroduce one.
- **Six type sizes, not ten.** `xs`, `xl` and `4xl` were deleted. 78% of all use had
  collapsed onto the two smallest sizes.
- **The landing is two screens**: a one-viewport hero plus `HowItWorks` below the fold.
  Its shell is `min-h-full` (the page scrolls) — only the scoring screen is `h-full`.

## Decisions that look like bugs but are deliberate

Do not "fix" these without reading the reasoning first.

- **Fusion weights are `supervised 1.00 / novelty 0.00 / evidence 0.00`.** Blending was
  measured and it destroyed 87% of PR-AUC at a realistic base rate. Reasoning is in
  `config/detect.yaml` — read the comment before touching it. Coverage is bought instead by
  `novelty_slots: 8` reserved queue positions.
- **Typology matchers are evidence generators, not detectors.** Rules alone score *below*
  the base rate (0.0030 vs 0.0039). They corroborate; they never rank.
- **Entropy is MAXIMAL for uniform distributions.** A matcher gating on low entropy to find
  a CoinJoin is inverted — this was a real bug. Use `output_uniformity`.
- **`min_observations: 1` in attribution.** Under randomised diffusion the originator's own
  announcement is frequently seen exactly once; requiring two discards the evidence we want.
- **Accuracy is reported beside an all-negative baseline** (0.9960 vs 0.9961). That is the
  point: at this base rate accuracy is meaningless. Judge on PR-AUC and MCC.

## Artefacts

`artifacts/v1/` = **demo** profile (564k rows). `artifacts/bulk/` = **bulk** profile
(2.47M rows, realistic 0.39% base rate) — **bulk is the honest one, quote it.**

## Commands

```bash
make bootstrap                             # clone -> demo: setup + generate samples
make verify-all                            # every host check
cd ui && npx tsc -b --force                # the real UI typecheck
make reproduce                             # regenerate every number from the seed
make docker-build && make docker-verify    # Linux, offline, 5 steps
make validate-external                     # Elliptic
make validate-elliptic-pp                  # Elliptic++
make serve                                 # API + UI on :8000
```

## How to work here

State what was measured, not what is expected. This project has repeatedly found that the
gap between "the machinery exists" and "it runs" hides real defects — the Docker path was
documented as ready and failed on first execution for two reasons. **If a claim has not been
executed, say so.**

Known open items:

1. **Explanation faithfulness is not measured.** SHAP reasons are shown to analysts but no
   deletion/insertion test proves the highlighted features drive the prediction.
2. **The censoring gap is reported, not closed.** Discrimination still depends on how much
   of an entity the capture actually saw — on demo, test ROC-AUC runs 0.76 on the thinnest
   quartile against 0.94 on the fullest (`metrics.json → results.test.censoring`). The
   correction features narrow it; nothing creates evidence that was never recorded. Quote
   the stratified numbers, not just the mean.

## This machine, and what is not installed on it

- System `python3` is **3.9**; the venv is **3.11**. Anything needing `match` statements
  (the pptx skill's `validate.py`, for one) will not run under the system interpreter.
- **No LibreOffice and no `pdftoppm`.** PDFs are produced by headless Chrome
  (`--print-to-pdf`) and slides are previewed by splitting a deck into one-slide files and
  running `qlmanage -t` on each. `ppt-build/render_slides.py` in the parent directory does
  exactly that.
- **The browser pane renders only at the instant of navigation.** Measured: zero rAF
  frames in 45 seconds while it is hidden, so canvas animation never paints and
  screenshots come back black. Verify UI work by measurement (geometry, computed style),
  not by eye — `docs/ui_architecture.md` §8 has the full trap list.

## Deliverables that live OUTSIDE this repo

In the parent `sih26/` directory, not tracked here:

- `BTC-FUSION_SIH2026_Idea.pptx` / `.pdf` — the SIH idea submission, built strictly on the
  official template (6 slides, Arial, header/footer/oval untouched). Team ID 112,
  team name `syntax112`. Built by `ppt-build/build.py`; `ppt-build/check_fit.py` measures
  every text box against its shape with real Arial metrics.
- `diagrams.html` — the original six plates. Predates the current UI; treat as historical.

Inside the repo, `docs/BTC-FUSION_architecture.pdf` (19 pages, 12 figures) is regenerated
from `docs/architecture_report.html` with headless Chrome.
