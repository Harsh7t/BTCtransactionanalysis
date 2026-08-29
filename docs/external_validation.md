# External validation — synthetic, and two real datasets

Every accuracy figure produced from our own generator is self-referential: we wrote the
data, so we know the answers. Three tracks address that, and they validate different parts
of the system.

| Track | Data | Validates | Does not validate |
|---|---|---|---|
| **A — synthetic** | our generator, seeded | the FULL network⇄chain fusion, end to end | absolute real-world detection rates |
| **B — real, transaction level** | Elliptic (public, labelled) | the CHAIN-SIDE detector, against published baselines | anything network-layer — Elliptic has no IPs |
| **C — real, ACTOR level** | Elliptic++ (Elmougy & Liu, KDD'23) | the unit we actually ship — address-level scoring, and the co-spend clustering heuristic | same: no IP layer anywhere in it |

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
make validate-external      # Track B, Elliptic
make validate-elliptic-pp   # Track C, Elliptic++
```

Elliptic++ needs `wallets_features_classes_combined.csv` and `AddrTx_edgelist.csv` in
`data/external/elliptic_pp/`, from <https://github.com/git-disl/EllipticPlusPlus>.

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

## Track C — Elliptic++, at the actor level

Track B validates a *transaction* classifier. This system ships an *entity* classifier, so
Track B validates something we do not ship. Elliptic++ adds 822,942 labelled wallet
addresses with 56 named features — lifetime in blocks, transaction counts, BTC sent and
received, fees, gaps between transactions, counterparty counts — the same quantities our
own entity features compute, at the same unit of analysis.

Artefact: `artifacts/v1/elliptic_pp_validation.json`. Reproduce with `make validate-elliptic-pp`.

### C1 — address classification

| | Value |
|---|---|
| PR-AUC | **0.3745** at a 5.56% base rate (6.7× lift) |
| Precision / Recall | 0.3711 / 0.4143 |
| F1 | 0.3915 |
| MCC | 0.3542 |

96,023 test addresses, trained on time steps 1–33 and tested on 34–49.

**Two traps in this dataset, both of which inflate the score if ignored.** 1,268,260 rows
cover 822,942 addresses — an address appears once per time step it was active in, and
illicit addresses recur about twice on average. A plain temporal split therefore puts the
same address in train *and* test with the same label, and the model scores it by memorised
identity rather than learned behaviour. The split is address-disjoint. Separately, the test
set is reduced to one row per address so that busier addresses do not carry more weight.

The artefact records the naive figure too (F1 0.3970 vs 0.3915). **Guarding against the
trap changed the result very little** — worth reporting precisely because it is a negative
finding, and because a reviewer cannot tell the difference between "we checked" and "we got
lucky" unless the check is in the artefact.

### C2 — the co-spend heuristic on real Bitcoin

Every clustering number elsewhere in this project is measured against a generator that was
told the right answer. This runs `graph/resolve.py`'s H1 (common-input-ownership) on the
real `AddrTx` edge list — 202,804 transactions, 400,212 addresses — and asks whether
addresses it groups together actually share a label.

| | Observed | Shuffled control | Lift |
|---|---|---|---|
| macro (per cluster) | **0.9979** | 0.8209 | **1.216** |
| micro (per pair) | 0.9960 | 0.8205 | 1.214 |
| micro, largest cluster excluded | 0.9939 | 0.8198 | 1.212 |

The control shuffles labels across the *same* clusters, holding the size distribution fixed,
because ~90% of labelled addresses are licit and almost any pairing agrees most of the time.
All three views agree, so the result does not rest on one big cluster.

**What this does and does not show.** Label agreement is necessary but not sufficient for
correct clustering: two unrelated *licit* actors merged together still agree. What it rules
out is gross over-merging across the illicit/licit boundary — the error that matters most
here, because an illicit actor absorbed into an exchange cluster disappears from the queue
entirely.

### What real data exposed that the generator never did

| | Synthetic (demo) | Real (Elliptic++) |
|---|---|---|
| addresses | 436,187 | 400,212 |
| entities resolved | 197,995 | 146,783 |
| mean addresses/entity | 2.20 | 2.73 |
| **largest single cluster** | **673** | **14,885** |

Comparable scale, and the largest real cluster is **22× bigger**. This is the documented
supercluster-collapse failure mode of common-input-ownership: exchanges co-spend across
customers, and the heuristic chains those merges until a large fraction of the network
collapses into one entity. **Our generator does not produce it**, so no synthetic figure in
this project reflects it — including the 0.9958 cluster purity. That is a limitation of the
data, found only by running on real Bitcoin, and it is now recorded in §7 of the write-up.

**H2 is not exercised here.** The change-address heuristic needs per-transaction timestamps
to decide which output was freshly minted, and Elliptic++ resolves time only to one of 49
coarse steps. Feeding it a 49-valued clock would manufacture change edges out of
tie-breaking rather than evidence, so H2 remains validated on synthetic data alone.

### Licence

The upstream repository states no licence. The files are gitignored and not redistributed.
Cite Elmougy & Liu, *Elliptic++: A Graph Network of Bitcoin Transactions and Wallet
Addresses*, KDD '23 — <https://github.com/git-disl/EllipticPlusPlus>.

## The claim this buys

> Chain-side detection is validated on real labelled Bitcoin data against published
> baselines. Network-side fusion is validated on synthetic data whose parameters are
> documented in `docs/generator_parameters.md`, with a measured sensitivity analysis
> showing how the conclusions move across the plausible range of observation coverage.

**Verify the published baseline yourself before citing it.** Do not repeat the figure in
`external.py` without confirming it from Weber et al. (2019) directly.
