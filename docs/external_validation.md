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
reports a score computed on nothing.

## The claim this buys

> Chain-side detection is validated on real labelled Bitcoin data against published
> baselines. Network-side fusion is validated on synthetic data whose parameters are
> documented in `docs/generator_parameters.md`, with a measured sensitivity analysis
> showing how the conclusions move across the plausible range of observation coverage.

**Verify the published baseline yourself before citing it.** Do not repeat the figure in
`external.py` without confirming it from Weber et al. (2019) directly.
