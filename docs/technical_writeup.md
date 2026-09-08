# BTC-FUSION — Technical Write-up

**SIH 2026 · PS 26146 · National Technical Research Organisation · Blockchain & Cybersecurity**

Every figure in this document is copied from `artifacts/v1/metrics.json`,
`leak_test.json`, `sensitivity.json` or `manifest.json`. `make reproduce` regenerates all
of them from a fixed seed. If a number is not in one of those files, it is not a result
and does not appear here.

**Two profiles are reported throughout.** `demo` (564,303 rows) is what the live
demonstration runs on, because it completes in 12 seconds. `bulk` (2,467,299 rows) is
what the numbers should be judged on, because its 0.39% positive rate is close to what an
analyst actually faces — the demo profile's 3.3% flatters the model. Where they differ,
**believe bulk**.

Artefacts: `artifacts/v1` (demo) and `artifacts/bulk`, feature version 7, seed 20260826,
132 features, backend `sklearn_histgb`.

---

## 1. Problem and scope

Bitcoin's pseudonymous P2P design lets criminal actors move, layer and cash out illicit
funds while evading conventional financial surveillance. Two independent evidence sources
could catch them, and each is useless alone: **the blockchain** records every transaction
but contains no people — addresses are random strings; **network traffic** records which
IP first announced a transaction but contains no meaning — packets carry no semantics.
This system joins them.

**A note on scope.** The PS references "Section 4 — Suggested AI/ML Focus Areas", and the
published text reads *"Attach Table Here of AI/ML Focus Areas."* **That table was never
published.** We therefore defined the detection scope ourselves, and state it plainly
rather than implying we followed a specification that does not exist:

- Eight actor archetypes (exchange, merchant, retail, miner, mixer, darknet market,
  ransomware, extortion) — covering all four crime types the PS background names.
- Six laundering typologies, **two held entirely out of training**.
- Alerting at two granularities: wallet-cluster (entity) and individual transaction.
- Bidirectional attribution: given an on-chain entity, which network identity is behind it.

## 2. Approach

The PS's load-bearing verb is **correlates**. Commercial chain analysis is a purchasable,
solved product; none of it ingests packet capture, because a private company cannot
lawfully tap an ISP. That capability gap is why this problem statement exists, and it is
the gap this system is built into.

Nine stages, one process, one container:

```
CSV/JSON/XML → ① INGEST → ② ENRICH → ③ RESOLVE → ④ GRAPH → ⑤ FEATURES
             → ⑥ DETECT+FUSE → ⑦ ATTRIBUTE → ⑧ EXPLAIN → ⑨ ALERTS
```

**Measured throughput: 565,670 rows end to end in 11.8 s.** Per-stage: ingest 0.73 s,
enrich 0.54 s, resolve 0.64 s, graph 0.19 s, features 8.51 s. 8-core CPU, no GPU.

Design choices that follow from the deployment context (air-gapped analyst workstation):
DuckDB not Postgres (a file, not a service); igraph in memory not Neo4j (no analytical
gain at this scale for another service to install); FastAPI in the same process as the
models (no serialisation boundary, no second service to die mid-demo); no authentication
(the OS is the access boundary).

## 3. Dataset

No data is provided and **no public dataset has a network layer**, so "collection" means
writing a defensible simulator. 1,680 lines, seeded, versioned.

Entity resolution recovers **197,995 entities from 436,187 addresses** via 159,726
co-spend edges (common-input-ownership) and 78,550 change edges (script-type-refined).
Mean cluster purity against ground truth: **0.9958** — clusters almost never merge two
real actors.

**Two typologies are held out of training entirely**: `dormancy_burst` and
`cross_asn_structuring`. Not one example appears in the train or calibration folds; the
split guard raises rather than warns if one does.

### The leak test — and the two defects it caught

We wrote the generator, so we know the answers, so every accuracy number is
self-referential. A sharp reviewer attacks the data, not the model. So `make leak-test`
trains a classifier on fields with **no constructed path to the label** and gates the
build on them scoring at the base rate.

**Result: PASS. Strict tier 1.242× baseline against 10.068× for the full feature set.**
The ~8× gap is the evidence that detection comes from topology, timing and network
structure rather than from an artefact of how the data was written.

Per-field: `round_number_frac` 1.000×, `ephemeral_linux_frac` 1.140×,
`mean_feerate_sat_vb` 1.145×, `ephemeral_windows_frac` 1.162×.

It has earned its keep twice:

1. **Crime proceeds were drawn from a different amount distribution than licit payments**
   (1.7× shortcut). Fixed: proceeds now use the same payment-size distribution, with the
   archetype controlling count and dispersion, never absolute scale.
2. **Mule wallets drew their OS from a different distribution than everyone else** (1.2×
   on ephemeral-port features) — the model was reading "no BSD hosts" as evidence of
   laundering.

Two indirect paths remain, both weak, both real-world rather than artefactual, and both
documented in `leak_test.json → known_residual`.

## 4. Model choice

| Model | Job | Why |
|---|---|---|
| Node2Vec (64-d) | structural roles | nobody labels "mixer-like topology"; the embedding discovers it. CPU-only |
| Gradient-boosted trees | primary classifier | best-in-class on tabular data; **SHAP is exact for trees**, not approximated |
| IsolationForest | novelty | linear-time, no distance assumptions, answers "what about patterns you never labelled?" |
| HDBSCAN | behavioural archetypes | doesn't need *k*, and explicitly labels noise — which is what an outlier is. Recovered **214 archetypes**, 60.9% noise |
| Isotonic regression | calibration | non-parametric, so it fixes arbitrary miscalibration shapes |

**GNNs were rejected on evidence, not taste.** Weber et al. (2019) found tree ensembles
outperformed a GCN on illicit-class F1 on exactly this task; GNNExplainer output is hard
to convert to analyst-readable prose; and a GNN is likelier to memorise generator
fingerprints. LightGBM is the reference backend; where its OpenMP runtime is unavailable
the system falls back to scikit-learn's HistGradientBoosting (the same histogram
algorithm) and **records which backend produced every number in the manifest**.

### Where the lift actually comes from

| Stage | demo PR-AUC | bulk PR-AUC |
|---|---|---|
| typology rules only | 0.0245 | 0.0030 |
| + unsupervised novelty | 0.1235 | 0.0207 |
| + GBDT on engineered features | 0.4516 | 0.2809 |
| + Node2Vec embeddings | **0.5483** | **0.3231** |
| + isotonic calibration (shipped) | 0.5291 | 0.3048 |

Rules alone sit at or below the base rate on both profiles — 0.0030 against a 0.0039 base
rate on bulk is *worse than chance*. **The lift is entirely the model**, which is what the
PS's "a working model, not just rules" asks for. Typology matchers never gate an alert;
they attach corroboration with real TXIDs to alerts the model already raised.

The final row is the cost of calibration, roughly 4%, and it buys a probability that means
something (ECE 0.041 on bulk).

### The fusion weights — a measurement that overturned our own design

The original design fused three signals into one ranking score, weighted
0.85 supervised / 0.05 novelty / 0.10 evidence, and the demo profile supported that: it
cost ~10% of PR-AUC and bought held-out recall.

**Training on the bulk profile showed the choice did not survive a realistic base rate.**

| Config | demo PR-AUC | **bulk PR-AUC** |
|---|---|---|
| classifier alone | 0.5483 | 0.3231 |
| 0.85 / 0.05 / 0.10 (original) | 0.4750 | **0.0382** |

An 88% collapse. Measuring each component on bulk explains it:

| signal, alone on bulk | PR-AUC | vs 0.0039 base rate |
|---|---|---|
| supervised classifier | 0.3231 | 83× |
| unsupervised novelty | 0.0207 | 5.3× |
| **typology evidence** | **0.0030** | **0.77× — below chance** |

*(All three are rows of the ablation table in `metrics.json`, not a separate experiment.)*

The evidence term carries no ranking signal at a realistic base rate, and because it is a
coarse near-binary value, weighting it at 10% promotes a broad band of unremarkable
entities above genuinely suspicious ones. We also tested rank-normalised blending, in case
this was a scale mismatch; it was not, and it made things slightly worse.

**Ranking is now the classifier's job alone (1.00 / 0.00 / 0.00).** The typology matchers
keep the role they were always specified for — evidence generators that corroborate an
alert in the case file — they simply no longer vote on the ordering.

Coverage of unlabelled typologies still matters, so it is bought differently: **eight of
sixty queue slots are reserved** for the highest-novelty entities the classifier did not
surface, tagged as a distinct row type. Blending corrupts every rank; reserving costs
exactly the slots it uses. This is also what Plate 04 always showed — a separate
`NO TYPOLOGY MATCH · UNSUPERVISED` row, not a blended score.

This is the finding we would most want a reviewer to ask about. Our own configuration was
wrong, our own measurement caught it, and the correction is in the artefacts.

## 5. Explainability method

Four layers, because "explainable" is a graded deliverable and not garnish.

1. **SHAP TreeExplainer** — exact per-alert attributions. Top influences on the shipped
   model: `max_n_outputs` 0.209, `emb_4` 0.069, `emb_1` 0.061, `degree_in` 0.060,
   `shared_infra_frac` 0.059.
2. **Narrative templating** — every feature carries the sentence describing the real-world
   behaviour it captures, and the direction is stated, never just the magnitude.
3. **Evidence chains** — typology matchers attach concrete, human-checkable corroboration:
   the actual TXIDs, the actual path, the actual amounts. This is what makes an alert
   *auditable* rather than merely explained.
4. **The counterfactual** — the case file states what evidence would raise or lower the
   confidence, computed by re-running the confidence model with one input changed. It is
   therefore a property of the model, not copywriting.

## 6. Evaluation

Metrics are chosen for a low positive rate. **Accuracy never judges this system**, and
where it appears it is always beside its own baseline — see below for why.

### Entity-level

| Metric | demo (564k, base 3.3%) | **bulk (2.47M, base 0.39%)** |
|---|---|---|
| test entities / positives | 14,083 / 463 | 59,043 / 232 |
| **PR-AUC** | 0.5291 (16× base) | **0.3048 (78× base)** |
| Precision @ 10 | 0.90 | 0.90 |
| Precision @ 50 | 0.92 | **0.90** |
| **ECE** | 0.0506 | **0.0405** |
| F1 | 0.5725 | **0.3969** |
| **MCC** | 0.5657 | **0.4017** |
| accuracy | 0.9753 | 0.9960 |
| *all-negative baseline* | *0.9671* | ***0.9961*** |

**Read the bulk column.** F1 falls from 0.57 to 0.40 because a 0.39% positive rate is
genuinely harder — the demo profile was flattering us. The *lift* over base rate improves
(16× → 78×), and precision holds at 0.90 in the top fifty, which is what an analyst
actually experiences.

**On accuracy.** On bulk the model scores **0.9960 against an all-negative baseline of
0.9961** — by accuracy, it is *worse than doing nothing*. That single line is the whole
argument for why this project reports PR-AUC and MCC, and treats accuracy as an artefact
that must never be shown without its control.

**On Precision@10.** It is the least reliable figure on this page: a bootstrap over the
test fold puts its 95% interval at roughly ±0.30, because it is computed over ten items.
**P@50 is the honest headline.**

### Why the late fold is harder — censoring, not drift

Discrimination falls across the temporally-forward splits. The reflex is to blame the
base rate, which falls with it, but ROC-AUC is prevalence-independent and cannot be
moved by the positive rate alone. Something about the late fold is genuinely harder, and
"the model degrades over time" is only one candidate explanation.

The other is **right-censoring**, and it is structural rather than a modelling failure.
A capture ends. An entity first seen a week before the end has one week of behaviour in
it however long it actually operated, so every aggregate — lifespan, burstiness,
transaction count, IP churn — is computed over a truncated window. A temporally-forward
split puts exactly those entities in the test fold.

Stratifying the test fold by the observation window each entity actually had separates
the two explanations, because they predict opposite patterns. Drift predicts a flat
deficit; censoring predicts recovery as the window grows. The measurement
(`metrics.json → results.test.censoring`, demo profile):

| observation window | n | illicit | ROC-AUC |
|---|---|---|---|
| under 7.4 days | 3,521 | 45 | **0.761** |
| 7.4 – 13.3 days | 3,520 | 88 | 0.865 |
| 13.3 – 18.5 days | 3,521 | 137 | 0.911 |
| over 18.5 days | 3,521 | 191 | **0.938** |

Monotone in the window. It is censoring. Entities that sent no transactions at all score
at **0.497** — chance — which is the same finding at its limit: almost every feature is
sender-side, so an entity we only ever saw receive is not scoreable by this model and
should be read as unranked rather than as cleared.

The same stratification on the **bulk** profile — the realistic 0.39% base rate, and the
one to quote — is steeper still: ROC-AUC runs **0.559 → 0.664 → 0.727 → 0.767** across the
same quartiles. The diagnosis replicates.

The *correction* does not replicate as cleanly, and it is reported as measured rather than
as hoped. Five features normalise the aggregates by the window that was actually available
— coverage of the window, transactions and value per available day, a right-censored flag,
and the span as a fraction of the capture — isolated as their own ablation row. On demo
they are worth **+0.042 PR-AUC** (0.432 → 0.475, an 8.5% relative gain). On bulk they are
**−0.004** (0.277 → 0.273): a wash. They are kept because the diagnosis they come from is
robust across both profiles and because they help most on the thin entities that matter
operationally, but anyone quoting the demo gain alone would be overclaiming.

The stratified table above is reported rather than averaged away,
because an operator deciding whether to act on a lead needs to know that a three-day-old
entity is scored with materially less confidence than a three-week-old one.

What is deliberately **not** a feature is the raw window length. It is monotone in
first-seen time, and this generator front-loads campaigns, so a model handed calendar
position would learn "late means licit" — an artefact of the dataset that would not
survive contact with a real one. Every censoring feature is a rate or a ratio that uses
the window only to normalise something else. `make leak-test` is the check, and it
passes.

### What the ranking metrics measure

Every ranking number in this document scores **the ordering an analyst is actually
shown**, which is not the same as scoring the model's probability. The queue ranks on the
raw fused score at full resolution and uses value moved only to break an exact tie; the
calibrated probability gates the queue and is displayed, but does not order it.

This distinction was not free. The system previously banded the calibrated probability to
two decimals and ordered by value moved *inside* each band, on the reasoning that two
entities at 0.93 are indistinguishable so the bigger money is the better lead. Measured on
the demo test fold, that reasoning is wrong: the calibrator's discarded resolution carries
real signal, and the banded ordering scored precision@25 of 0.88 and @50 of 0.92 against
1.00 and 1.00 for the raw score. Twelve points of precision at the top of the queue, for
nothing. `metrics.json → results.*.queue` now carries all three orderings side by side so
the choice stays evidenced rather than assumed.

### Two architectures we measured and did not ship

**Graph neural network message passing.** Two layers of mean aggregation over the payment
graph — written in closed form as `(A/deg) @ F` applied twice, so it needs no torch and
keeps SHAP exact — made the model worse: test raw PR-AUC 0.5786 without it, 0.5586 with
one hop, 0.5703 with two. The Node2Vec walks already encode structural role, and
re-supplying it as neighbourhood means adds thirty-two correlated columns and no
information. Removed. This is consistent with Weber et al. (2019), who found tree
ensembles outperformed a GCN on Elliptic.

**Positive-Unlabelled learning on Elliptic's discarded 77%.** See §6 Elliptic below.

Both are recorded because a negative result that cost a day is worth more than a
plausible architecture nobody checked — and because both are only trustworthy at all
because training became reproducible first. The same two comparisons run earlier moved
less than the run-to-run noise did.

### Generalisation to typologies never trained on

`dormancy_burst` and `cross_asn_structuring` are held out entirely — not one example in
the train or calibration folds, enforced by a guard that raises.

| | demo | bulk |
|---|---|---|
| held-out entities | 71 | 119 |
| recall at threshold | 0.2254 | **0.1176** |

Materially worse than the test score on both. **That gap is the finding** — the honest
bound on how the system behaves against a laundering pattern nobody anticipated.

### Transaction-level (§16.4-G)

137,273 transactions, 1,929 illicit (1.2% of the tested fold). **PR-AUC 0.1098 against a
0.0121 base rate — 9.1×.** P@10 0.90, P@50 0.40. A second model head over
transaction-local features plus the parent entity's score, split by the parent's fold so
no entity straddles the boundary. Weaker than the entity head, which is expected: a single
transaction carries far less signal than a wallet cluster's whole history.

### Attribution — the differentiator, measured

| Metric | demo | bulk |
|---|---|---|
| **Top-1 accuracy** | 0.9143 | **0.9321** |
| Random-choice baseline | 0.3449 | 0.3378 |
| Top-3 / MRR | 0.9153 / 0.9148 | 0.9328 / 0.9324 |
| Attempt rate | 98.6% | 98.9% |

A top-1 score is meaningless without knowing how many candidates it was chosen from, so
the candidate count and the chance baseline ship with it. The engine runs at **2.8×
chance**, and it *improves* with scale — more observations per entity is exactly what the
diffusion-aware weighting rewards.

### Attribution vs observation coverage — the honest curve

| Coverage | Top-1 | Chance |
|---|---|---|
| 5% | 0.593 | **0.740** |
| 10% | 0.671 | 0.585 |
| 20% | 0.781 | 0.396 |
| 35% | 0.862 | 0.284 |
| 100% | 0.901 | 0.200 |

**Below roughly 10% coverage the engine performs worse than guessing.** With almost no
observations it is mostly seeing relays rather than origin announcements, and it picks
among them confidently. That crossing point is a real limit of the method, measured rather
than argued, and left visible in the Model panel.

### Failure gallery

Six cases, reasons derived from each entity's own features. The informative ones are the
false positives on `transient` wallets: legitimate short-lived pass-through wallets are
structurally near-identical to laundering mules, and separating them needs counterparty
reputation this system deliberately does not model.

### Real labelled data — Elliptic (§16.4)

Every figure above comes from a generator we wrote, which makes them self-referential. The
Elliptic dataset (Weber et al. 2019) is real, public and hand-labelled, so it is the one
number here that is not.

| | Ours | Weber et al. 2019 |
|---|---|---|
| Illicit F1 | **0.7595** | 0.79 |
| PR-AUC | 0.8009 | not reported |
| Precision / Recall | 0.7858 / 0.7350 | — |
| MCC | 0.7439 | — |

46,564 labelled transactions at a 9.76% illicit rate. Trained on time steps 1-34, tested on
35-49 — forward in time, cut on a **step boundary** rather than at a positional 70% index,
because a positional cut splits a single time step across train and test. The test window
therefore spans the step-43 dark-market shutdown, the regime Weber et al. identified as the
hard one. `time_step` is both a feature and the split variable, so the harness refits
without it: PR-AUC 0.8026, F1 0.7518 — indistinguishable, so the score does not rest on the
time index.

Splits and feature subsets differ from the published work, so read 0.7595 against 0.79 as
*competitive with the published baseline*, not as a head-to-head deficit.

**What this does not validate.** Elliptic has 166 anonymised, publisher-aggregated features
and no network layer whatsoever — no IPs, no ports, no propagation timing. It exercises the
chain-side detector alone. It cannot touch the network⇄chain correlation this project is
built around. That division is the dual-track strategy in
[`docs/external_validation.md`](external_validation.md), stated up front rather than
discovered by a reviewer.

### Using the 77% of Elliptic that everyone discards

Elliptic labels 4,545 illicit and 42,019 licit transactions and leaves **157,205
unknown**. Our validation drops them, as does most published work on the set, because the
alternative — calling them licit — would silently mislabel a large illicit population.
That is 77% of a real, expensive, hand-collected dataset thrown away for want of a method.

Positive-Unlabelled learning is the third option. Under the SCAR assumption (labelled
positives are Selected Completely At Random from all positives), Elkan and Noto (KDD 2008)
show a classifier separating *labelled* from *unlabelled* is a constant multiple of the
true posterior, with the constant `c = P(labelled | illicit)` estimable on held-out
positives. Weighting each unlabelled example by its estimated positivity then lets those
106,371 training rows move the decision boundary instead of sitting outside the problem.

Both models scored on the same 16,670 held-out labelled transactions from the same later
time steps:

| | drop the unknowns | Positive-Unlabelled |
|---|---|---|
| PR-AUC | **0.8009** | 0.7710 |
| ROC-AUC | 0.9412 | **0.9493** |
| best F1 | **0.8259** | 0.7059 |

**It does not help.** PU wins marginally on ROC-AUC and loses on every metric that weights
the top of the ranking, which is the part an analyst works. The estimated `c = 0.9157`
explains why: the estimator concludes roughly 92% of illicit transactions are *already
labelled*, so the unknown pool is close to all-licit. If that is true there is almost
nothing to recover, and 106,371 softly-weighted rows buy variance instead of signal.

The caveat cuts both ways. SCAR is an assumption, and Elliptic's illicit labels came from
investigations, which do not sample uniformly — so `c` is an estimate under a condition
the dataset probably violates. That is precisely why it is read as *evidence about the
dataset* rather than as a constant of nature, and why the result is reported beside the
baseline rather than instead of it.

The value here is not a better number. It is that dropping the unknowns — the convention
every paper on this dataset follows — is now a decision with a measurement behind it. The
machinery is validated independently in `tests/test_external.py`, which hides a known
fraction of positives in the unlabelled pool and checks that `c` is recovered.

### Real labelled data at the ACTOR level — Elliptic++ (§16.4)

The Elliptic run above validates a *transaction* classifier; this system ships an *entity*
classifier. Elliptic++ (Elmougy & Liu, KDD'23) adds 822,942 labelled wallet addresses with
56 named features, at our unit of analysis. Artefact:
`artifacts/v1/elliptic_pp_validation.json`.

**Address classification.** PR-AUC **0.3745** at a 5.56% base rate (6.7× lift), F1 0.3915,
MCC 0.3542, over 96,023 test addresses; trained on time steps 1-33, tested on 34-49. The
split is **address-disjoint**: 1.27M rows cover 823k addresses, illicit ones recurring about
twice, so a plain temporal split would put the same address on both sides with the same
label and let the model score a memorised identity. The artefact also records the naive
figure (F1 0.3970) — guarding the trap changed little, which is worth stating precisely
because it is a negative finding.

**The co-spend heuristic, on real Bitcoin.** Every other clustering number here is measured
against a generator that knew the answer. Running `graph/resolve.py`'s H1 on the real
`AddrTx` edge list, addresses placed in the same cluster share a label **99.79%** of the
time (macro, per cluster) against a **82.09%** label-shuffle control — lift 1.216, and
stable at 1.212 with the largest cluster excluded. Agreement is necessary but not sufficient
for correct clustering — two unrelated licit actors merged still agree — but it rules out
gross over-merging across the illicit/licit boundary, which is the error that hides an
actor from the queue.

**What real data exposed that our generator does not produce.** The largest single address
cluster is **14,885 addresses on real Bitcoin versus 673 in our synthetic data**, at
comparable overall scale (400k vs 436k addresses). That is the documented supercluster
collapse of common-input-ownership, and our generator has no analogue of it. See §7.

## 7. Limitations

The section most teams omit and an NTRO reader will respect most.

- **Every synthetic figure is self-referential.** We wrote the generator. The leak test
  bounds this — 1.242× against 10.068× — it does not eliminate it.
- **Generator parameters are engineering defaults, not literature-sourced values.** See
  `docs/generator_parameters.md`. Until they are sourced, the defensible claim is about
  the *method and system*, not the absolute detection rate.
- **Class balance still exceeds a real base rate**, though the bulk profile narrows the
  gap: 0.39% at entity level and 0.44% at transaction level. It drifts across folds
  because laundering campaigns cluster in time and the split is temporally forward.
- **Precision@10's confidence interval is wide.** Quote P@50.
- **Entity resolution is high-precision, moderate-recall.** Purity 0.9958, but 164,414 of
  197,995 demo entities are singletons — receive-only addresses fragment — correct behaviour for these heuristics, and it
  means the entity count far exceeds the true actor count.
- **Our generator does not reproduce supercluster collapse.** On real Bitcoin the largest
  common-input-ownership cluster reaches 14,885 addresses; on our synthetic data of
  comparable size it reaches 673. Exchanges co-spend across customers and the heuristic
  chains those merges until much of the network collapses into one entity. No synthetic
  number here reflects that — including the 0.9958 cluster purity, which should be read as
  "correct on data without superclusters", not as a real-world expectation. Found only by
  running on Elliptic++; see `docs/external_validation.md` Track C.
- **Attribution degrades with coverage and inverts below ~10%.** See the curve above.
- **Our own fusion weights were wrong until the bulk run.** They were tuned at a 3.3%
  positive rate and lost 88% of PR-AUC at 0.39%. Any hyperparameter chosen on one base
  rate should be assumed invalid at another until re-measured — including the ones we
  ship now.
- **Single observations cannot support confident attribution, by design.** Bitcoin Core's
  randomised per-peer relay delay exists precisely to defeat first-relay inference
  (Koshy FC'14, Biryukov CCS'14; Dandelion++ BIP-156 proposed, never merged). We model the
  defence rather than ignoring it.
- **Only the chain half is validated on real data.** The Elliptic run
  (`make validate-external`) reaches **illicit F1 0.7595, PR-AUC 0.8009** on 46,564 real
  labelled transactions, trained on time steps 1-34 and tested on 35-49 - competitive with
  Weber et al.'s published 0.79 under a different split. That validates the chain-side
  detector and nothing else: Elliptic has no IP, port or timing layer, so the
  network-chain correlation that is this project's actual thesis is still measured only
  against a generator we wrote ourselves. Elliptic++ (Elmougy & Liu, KDD'23) would add a
  real address graph and address-level labels, closing more of the chain-side gap - and
  none of the network-side one. No public dataset closes that gap; it needs a real
  multi-vantage-point listener deployment.

## 8. Reproduction

```bash
make reproduce      # generate → leak-test → train → score, from a fixed seed
make verify-all     # every check a judge could run, on the host
make docker-build && make docker-verify   # the same, on Linux, with NO network
```

`docker-verify` runs five steps under `--network none`: the test suite, which ML backend
Linux resolves (LightGBM 3.3.5), an offline GeoIP lookup, the full pipeline on 564k rows,
and a check that the container reproduces the host's model outputs bit-for-bit. That last
step exists because the container installs scikit-learn 1.7.2 while the artefacts were
pickled by 1.9.0; the scores match exactly today, and the check fails the build if a future
re-vendor changes that.

Three artefact files carry every number: `metrics.json`, `leak_test.json`,
`manifest.json`. The manifest records the input's SHA-256 (`f090a003…`), the seed
(20260826), the feature version (7), the model backend and the git SHA.

The feature matrix is byte-reproducible from seed, enforced by a golden-file test. That
test found a real defect: `active_entities` returned Polars `group_by` order, which is
non-deterministic, so igraph vertex indices moved between runs and betweenness sampled
different pivots — **fixed-seed runs were producing different feature matrices**. Nothing
but a golden file would have caught it.
