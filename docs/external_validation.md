# External validation — the dual track

Every accuracy figure produced from our own generator is self-referential: we wrote the
data, so we know the answers. Two independent tracks address that, and they validate
different halves of the system.

| Track | Data | Validates | Does not validate |
|---|---|---|---|
| **A — synthetic** | our generator, seeded | the FULL network⇄chain fusion, end to end | absolute real-world detection rates |
| **B — real** | Elliptic (public, labelled) | the CHAIN-SIDE detector, against published baselines | anything network-layer — Elliptic has no IPs |

## Why not train everything on Elliptic

Its 166 features are anonymised and aggregated by the publisher, and it has **no network
layer at all** — no IPs, no ports, no timing. It cannot exercise the correlation
requirement that is the entire point of PS 26146. It is a validation set, not a training
set.

## Obtaining the data

Not committed — licence and size. Download `elliptic_txs_features.csv` and
`elliptic_txs_classes.csv` from the Elliptic Data Set on Kaggle into
`data/external/elliptic/`, then:

```bash
make validate-external
```

Absent the files, the harness reports `available: false` with instructions. It never
reports a score computed on nothing. The CSVs are gitignored.

## Result — measured 2026-08-29

Artefact: `artifacts/v1/external_validation.json`. Reproduce with `make validate-external`.

| | Ours | Weber et al. 2019 |
|---|---|---|
| Illicit F1 | **0.7595** | 0.79 |
| PR-AUC | 0.8009 | not reported |
| Precision | 0.7858 | — |
| Recall | 0.7350 | — |
| MCC | 0.7439 | — |

46,564 labelled transactions, 9.76% illicit. Trained on time steps 1–34, tested on 35–49.

Three things to say out loud about that number, because a reviewer will find them anyway:

**The split is forward in time and cut on a step boundary.** Not a random split, and not a
positional 70% cut — a positional cut lands *inside* a time step and puts contemporaneous
transactions on both sides of a boundary whose entire purpose is to separate them in time.
The test window therefore contains the step-43 dark-market shutdown, the regime where
Weber et al. found performance degrades. This is the harder setup, not the flattering one.

**`time_step` is both a feature and the split variable**, so the harness refits without it
and records the outcome: PR-AUC 0.8026, F1 0.7518 — statistically indistinguishable. The
score does not rest on the time index. That is measured, not asserted.

**Splits and feature subsets differ from the published work**, so 0.7595 against 0.79 means
"competitive with the published baseline", not "0.03 worse than it". Do not present it as a
head-to-head.

## The claim this buys

> Chain-side detection is validated on real labelled Bitcoin data against published
> baselines. Network-side fusion is validated on synthetic data whose parameters are
> documented in `docs/generator_parameters.md`, with a measured sensitivity analysis
> showing how the conclusions move across the plausible range of observation coverage.

**Verify the published baseline yourself before citing it.** Do not repeat the figure in
`external.py` without confirming it from Weber et al. (2019) directly.
