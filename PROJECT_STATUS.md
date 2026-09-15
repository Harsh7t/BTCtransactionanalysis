# PROJECT_STATUS.md — where BTC-FUSION stands

**Last updated: 16 September 2026.** Update this file at the end of every working session:
what changed, what was verified, what is still open.

SIH 2026 · PS 26146 (National Technical Research Organisation) · Blockchain & Cybersecurity.
Team `syntax112`, team ID 112. Repository: `github.com/Harsh7t/BTCtransactionanalysis`,
branch `main`.

BTC-FUSION ingests bulk Bitcoin transaction and network metadata, joins the **network
layer** (IP, port, timing) to the **chain layer** (addresses, TXIDs, amounts), and produces a
ranked, explainable queue of investigative leads — fully offline, in one process.

---

## Read in this order

1. `README.md` — how to install and run the demo.
2. **This file** — current state, open items, where the deliverables are.
3. `ENGINEERING.md` — environment traps, rules the codebase enforces, decisions that look
   like bugs but are deliberate. **Read before changing anything.**
4. `DESIGN.md` — architecture and the reasoning behind each key decision.
5. `docs/` — `technical_writeup.md` (approach and evaluation), `model_card.md`,
   `attribution_method.md`, `external_validation.md`, `generator_parameters.md`,
   `ps_compliance.md` (every PS requirement → the command that verifies it),
   `ui_architecture.md` (the interface and its traps).

---

## What is built — and how it was verified

| Part | State | Evidence |
|---|---|---|
| Nine-stage pipeline (`btcfusion/`) | working | `make run`; live UI runs score 564,303 rows in ~14–16 s |
| Test suite (`tests/`, 16 files) | **88 passed** | `make test`, last run 14 Sep 2026 |
| Trained artefacts | `artifacts/v1` (demo), `artifacts/bulk` | trained 7 Sep 2026, git `5a20a09`, backend `sklearn_histgb`, 141 features |
| Reproducibility | byte-identical reruns | `tests/test_determinism.py` |
| Generator leak test | PASS | strict tier 1.247× vs 10.795× control, gate 1.30× |
| Offline Linux container | 5/5 steps passed | `make docker-verify` — **run when the suite had 81 tests; not repeated since** |
| Real-data validation | done | Elliptic F1 0.7595 (published 0.79); Elliptic++ address PR-AUC 0.3745 |
| Analyst UI (`ui/`, React + TypeScript) | working, built bundle committed in `ui/dist/` | landing, scoring, Alerts (table · dossier · focus), case file, link graph, Model, Provenance |

## Headline numbers (read from the artefacts — quote bulk)

| | demo · `artifacts/v1` · 564,303 rows | **bulk · `artifacts/bulk` · 2,467,299 rows** |
|---|---|---|
| test positive rate | 3.27% | **0.39%** |
| PR-AUC of the ranking the analyst sees | 0.5889 | **0.2998 (77× base rate)** |
| precision @ 10 / 25 / 50, shipped queue | 1.00 / 1.00 / 0.98 | **1.00 / 0.96 / 0.92** |
| calibration error (ECE) | 0.0393 | 0.0381 |
| held-out typology recall | 0.2113 | 0.1176 |
| attribution top-1 (random choice) | 0.9052 (0.3449) | **0.9243 (0.3378)** |
| attributions suppressed as shared infrastructure | 5,694 | 28,661 |
| addresses → actors | 436,187 → 197,995 | 1,810,005 → 829,821 |
| rules alone (ablation) | 0.0244 | 0.0030 — below the 0.0039 base rate |

The Model screen's scorecard ranks by the **calibrated probability** (demo P@10 0.80). The
queue itself ranks by the **raw score** (P@10 1.00). Both are true — say which one you quote.

---

## Recent work

**Committed and pushed — `e7e99dc` (14 Sep 2026):**
- Landing page no longer renders blank under `prefers-reduced-motion` (negative canvas
  radius in `ui/src/components/Propagation.tsx`).
- Case-file counterfactuals only say "falls to" when the confidence actually falls
  (`btcfusion/attribute/confidence.py`, new `tests/test_counterfactuals.py`).
- Alert queue layouts: table (default), dossier, focus — `ui/src/components/QueueViews.tsx`.
- UI copy: 141 features, bulk-profile figures, sample timings. README reproducibility note.
- `docs/architecture_report.html` → `docs/BTC-FUSION_architecture.pdf` (24 pages), every
  figure re-read from the artefacts, new §12 on the analyst interface.

**Documentation refresh (16 Sep 2026):**
- `DESIGN.md` (new) and `PROJECT_STATUS.md` (new).
- `ENGINEERING.md`, `REPRODUCE.md`, `README.md`, `docs/technical_writeup.md`, `docs/model_card.md`,
  `docs/ps_compliance.md`, `docs/attribution_method.md`, `docs/generator_parameters.md`,
  `docs/ui_architecture.md` — stale figures refreshed against the current artefacts.

---

## Running the demo

```bash
cd btc-fusion
make serve                      # API + UI on http://localhost:8000
```

- **On this development machine, port 8000 is taken by an unrelated app.** Run
  `.venv/bin/python -m btcfusion.cli serve --port 8011` and open http://localhost:8011.
- The demo is presented in the **light theme** on a laptop. Click **DEMO** to score the
  564k-row sample live (~15 s), or **view last run** to go straight to the 60 alerts.
- Sample captures are generated, never committed: `make bootstrap` creates them.

---

## Deliverables outside the repo (`~/Desktop/sih26/`)

| File | What | Rebuild with |
|---|---|---|
| `BTC-FUSION_SIH2026_Idea.pptx` and `ppt-build/BTC-FUSION_SIH2026_Idea.pdf` | SIH idea submission, 6 slides on the official template | `cd ppt-build && .v311/bin/python build.py`, then `_hires.py` to render |
| `BTC-FUSION_Project_Guide.pdf` | 39-page guide and pitch kit | edit `guide-build/project_guide.html`, print with headless Chrome |
| `btc-fusion/docs/BTC-FUSION_architecture.pdf` | 24-page technical report | print `docs/architecture_report.html` with headless Chrome |
| `diagrams.html` | six diagram plates (architecture, process, use case, three wireframes) | `python3 ppt-build/gen_diagrams.py` with a server on :8011 |
| `BTC-FUSION_Documentation.pdf`, `BTC-FUSION_Pitch_Script.pdf`, `Design.pdf` | older documents | **stale — superseded by the guide** |
| `SIH26146_Roadmap.md` | original roadmap | historical |

---

## Open items, in priority order

1. **Before submitting the PPT**, verify two references on slide 6 against their sources:
   FATF's 2021 updated guidance on virtual assets, and India's March 2023 notification
   bringing virtual-digital-asset service providers under the PMLA.
2. **Re-run the offline container check** (`make docker-build && make docker-verify`) — the
   suite has grown from 81 to 88 tests since it last ran.
3. **Explanation faithfulness is unmeasured.** No deletion/insertion test shows the SHAP
   features actually drive each prediction.
4. **The censoring gap is reported, not closed.** Bulk ROC-AUC runs 0.559 on the shortest
   observation-window quartile to 0.767 on the longest.
5. **UI:** the Model scorecard shows calibrated-order precision (0.80) while the queue ships
   raw-score order (1.00); showing both would stop a judge reading it as a contradiction.
6. **UI:** counterfactual lines do not name which candidate IP they refer to.
7. **Network half validated only on synthetic data.** No public dataset has an IP layer;
   closing this needs a real multi-vantage-point capture.

---

## Working rules that have bitten before

- **No AI-tool attribution anywhere** — no `Co-Authored-By` trailers, no "generated with"
  lines, no tool names in commits, PR descriptions, docs or slides. Commits are authored as
  Harshit Sengar.
- **Every number must come from an artefact file** (`artifacts/*/metrics.json`,
  `leak_test.json`, `manifest.json`, `sensitivity.json`) or a stated live run — and say
  whether it is demo or bulk.
- **State what was executed, not what was built.** "The machinery exists" has hidden real
  defects in this project more than once.
- **Publish weaknesses as prominently as strengths** — measured bad numbers beat unmeasured
  good ones.
- **Never commit** `data/samples/` or `data/external/`. **Do commit** `ui/dist/` after `make ui`.
- The UI must not look template-generated; the demo is judged in light theme.
