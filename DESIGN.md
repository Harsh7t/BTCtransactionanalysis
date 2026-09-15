# DESIGN.md — how BTC-FUSION is put together, and why

SIH 2026 · PS 26146 (NTRO) — correlate Bitcoin **network-layer** traffic (IP, port,
timing) with **blockchain-layer** activity (addresses, TXIDs, amounts) to produce a
ranked, explainable queue of investigative leads. Offline, single process, single file
of state.

This document is the architecture: components, data flow, and the decisions that shaped
them. It does not repeat what other docs already settle — see the table below.

| Question | Answer lives in |
|---|---|
| What is the approach, and how well does it score? | `docs/technical_writeup.md` |
| What does the interface look like, and why? | `docs/ui_architecture.md` |
| Statistics behind network↔chain attribution | `docs/attribution_method.md` |
| Every synthetic-data parameter | `docs/generator_parameters.md` |
| Intended use, failure modes | `docs/model_card.md` |
| Build gotchas, environment traps | `ENGINEERING.md` |
| How to regenerate every published number | `REPRODUCE.md` |

## 1. Design goals

These are the constraints the architecture optimises for, in order:

1. **Offline.** No API key, no cloud model, no network call at runtime. `make
   offline-check` enforces this by grepping for `https?://` in application code. This
   rules out anything that needs a hosted LLM or a managed vector store.
2. **Explainable, not just accurate.** Every alert carries exact SHAP values (not an
   approximation), the real TXIDs that prove it, and — for attribution — a
   counterfactual stating what evidence would change the model's mind. A number with no
   reasoning attached is not a deliverable here.
3. **Never fabricate confidence.** Where the evidence cannot support a claim (an IP
   resolves to shared infrastructure; observation coverage is too low), the system
   abstains rather than guessing. This is why attribution has a `suppressed` status and
   why the queue reports how many entities were held back, not just the ones shown.
4. **Reproducible.** One seed, one command (`make reproduce`) regenerates every
   published figure byte-for-byte. A number that cannot be regenerated does not go in a
   document — this is enforced by convention, not by tooling, so it is worth restating
   here.
5. **Degrade, never fail.** A stack trace in front of an analyst is the one
   unacceptable outcome. If model artefacts are missing, scoring falls back to
   unsupervised + typology evidence. If a capture has no IP columns, the run drops to
   chain-only mode. If attribution raises, alerts still ship and the panel says
   "unavailable".

## 2. Non-goals

- **Not a microservice architecture.** One Python process serves the API and holds the
  trained models in memory — see §4 for why.
- **Not a real-time/streaming system.** Captures are scored in batch; the UI shows
  progress through nine stages, not a live feed.
- **Not evidence, not automated action.** The output is a lead for a human analyst.
  Nothing here blocks a transaction or freezes an account.
- **Not a detection-rate claim on real crime.** Training data is synthetic (§6); real
  Bitcoin only appears in validation (Elliptic, Elliptic++), never in training.

## 3. System at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTATION — React + TypeScript (ui/)                        │
│  Alert Queue · Case File · Link Analysis · Model · Provenance   │
└───────────────────────────┬───────────────────────────────────--┘
                             │ REST / JSON
┌───────────────────────────▼───────────────────────────────────--┐
│  SERVICE — FastAPI + uvicorn (btcfusion/api/main.py)             │
│  same process as the models: no serialisation boundary,          │
│  nothing that can fail independently during a demo               │
└───────────────────────────┬───────────────────────────────────--┘
                             │
┌───────────────────────────▼───────────────────────────────────--┐
│  ANALYTICS CORE — nine stages (btcfusion/pipeline.py)             │
│  ingest → enrich → resolve → graph → features →                  │
│  detect+fuse → attribute → explain → store                       │
└───────────────────────────┬───────────────────────────────────--┘
                             │
┌───────────────────────────▼───────────────────────────────────--┐
│  PERSISTENCE — DuckDB (one file) · igraph (in memory, per run) ·  │
│  artifacts/{v1,bulk} (pinned models + metrics + manifest)         │
└───────────────────────────────────────────────────────────────--┘
```

Everything below "PRESENTATION" runs inside one Python process. There is no queue,
no cache layer, no second service — see §4.

## 4. Key decision: one process, not a service mesh

FastAPI, the trained models, and DuckDB all live in one Python process
(`btcfusion/api/main.py` imports `pipeline.py` directly; there is no RPC).

**Why:** the deployment target is a single analyst workstation, air-gapped, no ops
team. A service boundary between the API and the model buys isolation at the cost of a
serialisation format, a second thing to start, and a second thing that can be down
during a demo. DuckDB is a file, not a server — `store/dao.py` opens it directly.
igraph is rebuilt in memory per run rather than persisted, because a run's graph is
only needed for that run's link analysis.

**Trade-off accepted:** this does not horizontally scale, and a crash in the analytics
core takes the API with it. Both are fine for the target deployment and wrong for a
multi-tenant SaaS version — if this ever needs to serve concurrent investigators, this
is the first thing to revisit.

## 5. Data flow: the nine stages

`btcfusion/pipeline.py` (`run_pipeline`) is the single place that owns this sequence;
the API calls it, the CLI calls it, tests call it. It is deliberately not
re-implemented anywhere else.

| # | Stage | Module | Does |
|---|---|---|---|
| 1 | Ingest | `ingest/parsers.py`, `ingest/schema.py` | CSV/JSONL/XML → one internal frame. Bad rows are quarantined with a reason, never silently dropped. |
| 2 | Enrich | `ingest/enrich.py` | IP → ASN, country, host class (residential/mobile/hosting/VPN/Tor) from a bundled offline GeoIP database. |
| 3 | Resolve | `graph/resolve.py` | Common-input ownership + change-address heuristic collapses addresses into actors. |
| 4 | Graph | `graph/build.py` | Actor-to-actor money flow (igraph) plus the sparse entity × IP co-occurrence matrix attribution needs. |
| 5 | Features | `features/extract.py`, `features/embeddings.py` | 141 features per actor: 77 engineered (chain, network, timing, graph) + 64 Node2Vec dimensions (PPMI-SVD). |
| 6 | Detect + Fuse | `detect/supervised.py`, `detect/novelty.py`, `detect/typologies.py`, `detect/fuse.py` | Three signals computed side by side — see §7. |
| 7 | Attribute | `attribute/engine.py`, `attribute/significance.py`, `attribute/confidence.py`, `attribute/diffusion.py`, `attribute/infra.py`, `attribute/behaviour.py` | Hypergeometric co-occurrence test + Benjamini–Hochberg FDR (α 0.01) → entity ⇄ IP with a confidence interval and counterfactuals, or abstain. |
| 8 | Explain | `explain/narrative.py`, `explain/report.py` | Exact SHAP (TreeExplainer) → English narrative, plus the case-file export. |
| 9 | Store | `store/dao.py` | DuckDB: runs, alerts, verdicts, provenance receipt. |

`run_pipeline` returns the receipt (row counts, quarantine reasons, per-stage timings,
entity-resolution stats) and writes everything else to DuckDB — the UI reads it back
through the API, never from pipeline return values directly, so a page refresh always
shows what was actually persisted.

## 6. Key decision: rules attach evidence, they never raise an alert

Stage 6 runs three signals in parallel, and they are not peers:

- **Gradient-boosted trees** (`detect/supervised.py`, `sklearn_histgb`/LightGBM) —
  supervised, trained on known typologies. This is what **ranks the queue**
  (`config/detect.yaml`: fusion weights `supervised 1.00, novelty 0.00, evidence 0.00`).
- **IsolationForest + HDBSCAN** (`detect/novelty.py`) — unsupervised, catches
  behavioural patterns nobody labelled. Reserves `novelty_slots` (8 of 60) of the
  queue so a genuinely new pattern cannot be starved out by known typologies scoring
  higher (`pipeline.py`, alert-selection block).
- **Typology matchers** (`detect/typologies.py`) — peel chain, fan-in/out, rapid
  layering, mixer passthrough, dormancy burst, cross-ASN structuring. These attach
  **evidence** to a narrative (`evidence_strength`) but carry zero weight in the fused
  score. A rule that could raise an alert on its own is indistinguishable from "a
  working model" only on the cases it happens to cover.

**Why the classifier ranks alone:** measured on the held-out test fold, rules alone
score below the base rate (`docs/technical_writeup.md` §ablation). Splitting "decide"
from "corroborate" is what lets the case file say *both* "the model flagged this" *and*
"an independent rule-based check agrees" without conflating the two into one number
that could be gamed by tuning the rules to the test set.

## 7. Key decision: rank on the raw score, calibrate for display only

Isotonic regression (`detect/fuse.py`, `Calibrator`) turns the fused score into an
honest probability — 0.90 means roughly a 90% chance, measured (ECE ~0.04 on the demo
test fold). But isotonic output is a step function: its top bin is flat, so ranking by
it collapses dozens of distinct leads into an arbitrary tie order.

The queue therefore **ranks on the raw fused score** (full resolution, ties broken by
value moved) and uses the calibrated probability only to **gate** the threshold and to
**display** the confidence number. This was measured, not assumed — a banded ordering
(round confidence to 2dp, sort by value inside the band) was the original design and
scored 12 points of precision worse at the top of the queue on the bulk profile.
`metrics.json → results.*.queue` keeps all three orderings side by side so the choice
stays evidenced, not just asserted here.

## 8. Key decision: attribution can say "no" and explain why

`attribute/engine.py` runs a hypergeometric test on every actor–IP pair, with
Benjamini–Hochberg FDR control across all pairs tested (not per-pair — a naive
per-pair threshold would produce thousands of false positives at this row count).
Diffusion-aware weighting favours propagation-tree roots over first-observation
(`attribute/diffusion.py`), and an infrastructure penalty (`attribute/infra.py`)
discounts VPN/Tor/hosting IPs multiplicatively rather than excluding them outright.

When every candidate IP resolves to shared infrastructure, the engine returns
`suppressed` rather than naming the least-bad candidate. This is the single design
decision most worth defending in a Q&A: an attribution tool that always names someone
is easier to build and useless to trust. `attribute/confidence.py` also computes
**counterfactuals** — the same confidence function re-run with one input changed (a
VPN-exit penalty applied, or three times the observations) — so the case file states
what evidence would change its own conclusion, not just what the conclusion is.

## 9. Key decision: synthetic training data, gated by a leak test

There is no public dataset that pairs Bitcoin transactions with the network-layer
observations (IP, port, timing) this project correlates against — that pairing is the
project's contribution, and nobody has published ground truth for it. Training data is
therefore generated (`btcfusion/generator/`) from a fixed seed, with actor archetypes
and named laundering typologies (two held out entirely, to measure generalisation
honestly — see `docs/technical_writeup.md`, held-out typology recall).

**The risk this creates:** a generator can accidentally encode its own labels in a
field the model then "detects" for free — the model would be perfect and it would be
worthless. `btcfusion/generator/leak_test.py` guards against this directly: it trains
a classifier on fields with *no constructed path* to the label (fee rate, OS port
fingerprint, round-number fraction) and requires it to score near the base rate. This
runs automatically in `make reproduce` and fails the build above a 1.30× lift gate.
Real Bitcoin data (Elliptic, Elliptic++) is used only for **validation**, never for
training — `docs/external_validation.md` covers what that does and does not prove.

## 10. Frontend structure

`ui/` is React + TypeScript, built with Vite, styled with Tailwind. `ui/dist/` is
committed on purpose — `make serve` serves that bundle directly, and a fresh clone
without it shows a blank page (see `ENGINEERING.md`).

Screens (`ui/src/components/`): `StartScreen` (landing, sample/upload picker) →
`Processing` (nine-stage progress) → `AlertQueue` (the triage queue; `QueueViews.tsx`
holds the table/dossier/focus layouts) → `CaseFile` (one lead, full detail) →
`GraphView` (Cytoscape-driven link analysis) → `ModelPanel` (calibration, ablation,
failure gallery) → `Provenance` (the run manifest). `stages.ts` is the single source
of truth for the nine-stage copy, shared between the landing page's explainer and the
live progress screen so they cannot drift apart.

Design rationale, colour semantics, motion rules and the traps that have already bitten
someone are in `docs/ui_architecture.md` — this file only states that it exists and
where the layout switch lives.

## 11. Repository layout

```
btc-fusion/
├── btcfusion/         analysis engine — see §5 table for what each subpackage does
│   ├── api/           FastAPI app; the only place that imports pipeline.py for serving
│   ├── ingest/        parse, validate, enrich
│   ├── graph/         address resolution, entity graph
│   ├── features/      engineered + Node2Vec features
│   ├── detect/        supervised, novelty, typology, PU-learning, fusion
│   ├── attribute/     network ⇄ chain attribution engine
│   ├── explain/       SHAP → narrative, case-file export
│   ├── eval/          metrics, splits, sensitivity, external validation
│   ├── generator/     synthetic data + the leak test that guards it
│   ├── store/         DuckDB access
│   ├── pipeline.py    orchestrates all nine stages
│   ├── train.py       trains and pins artifacts/{profile}
│   └── cli.py         `btcfusion <command>` entry points used by the Makefile
├── ui/                React + TypeScript interface (see §10); ui/dist/ is committed
├── config/            generator.yaml, detect.yaml, schema_map.yaml — the knobs
├── artifacts/         v1 (demo profile) and bulk — pinned models + metrics + manifest
├── data/              geo/ (bundled GeoIP), samples/ + external/ (generated/downloaded, gitignored)
├── docs/              the documents in the table at the top of this file
├── tests/             unit, property, determinism, external-validation tests
├── scripts/           geoip fetch, offline verification, wheel vendoring
├── wheels/            vendored Linux wheels so `docker build` needs no network
├── Makefile           setup, bootstrap, train, run, serve, test, reproduce, verify-all
└── Dockerfile          --platform linux/amd64 required on Apple Silicon (ENGINEERING.md)
```

## 12. Where these decisions are enforced

Design intent decays into "it happened to work once" unless something checks it on
every change:

- `make offline-check` — greps `btcfusion/` for `https?://`; fails the build if
  application code references a remote host.
- `make leak-test` (part of `make verify-all`) — fails above a 1.30× strict-tier lift;
  gates §9.
- `tests/test_determinism.py` — two runs from the same seed must produce byte-identical
  output across separate processes; guards the three ordering bugs documented in
  `ENGINEERING.md`.
- `tests/test_attribution_eval.py`, `tests/test_sensitivity.py` — attribution accuracy
  is graded against ground truth and against a random-choice baseline, and must degrade
  as observation coverage falls; a static assertion could not catch a regression here.
- `tests/test_counterfactuals.py` — every "what would change this" line is checked to
  move the confidence in the direction its sentence claims.
- `tests/test_external.py`, `tests/test_elliptic_pp.py` — validation against real
  Bitcoin degrades cleanly (does not crash) when the datasets are absent, since they
  are gitignored and not everyone will have downloaded them.

If a change to this system contradicts a decision in this document, the fix is either
the change or this document — never let them silently disagree.
