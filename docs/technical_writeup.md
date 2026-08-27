# BTC-FUSION — Technical Write-up

**SIH 2026 · PS 26146 · National Technical Research Organisation · Blockchain & Cybersecurity**

Every figure in this document is copied from `artifacts/v1/metrics.json`,
`leak_test.json`, `sensitivity.json` or `manifest.json`. `make reproduce` regenerates all
of them from a fixed seed. If a number is not in one of those files, it is not a result
and does not appear here.

Artefacts described: `artifacts/v1`, feature version 7, seed 20260826, 132 features,
42,245 training entities, backend `sklearn_histgb`, git `dab45c0`.

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

| Stage | Test PR-AUC | P@10 |
|---|---|---|
| typology rules only | 0.0245 | 0.00 |
| + unsupervised novelty | 0.1235 | 0.10 |
| + GBDT on engineered features | 0.4402 | 1.00 |
| + Node2Vec embeddings | **0.5239** | 1.00 |
| + fusion & calibration (shipped) | 0.4635 | 1.00 |

Rules alone sit near the 0.0329 base rate. **The lift is the model** — which is precisely
what the PS's "a working model, not just rules" asks for. Typology matchers never gate an
alert; they attach corroboration with real TXIDs to alerts the model already raised.

### The fusion weights are a measured choice, not a preference

| supervised / novelty / evidence | Test PR-AUC | P@10 | Held-out recall |
|---|---|---|---|
| 1.00 / 0.00 / 0.00 | 0.5148 | 1.00 | 0.2113 |
| **0.85 / 0.05 / 0.10 (shipped)** | **0.4637** | **1.00** | **0.2394** |
| 0.65 / 0.25 / 0.10 | 0.4341 | 1.00 | 0.2817 |

Leaning entirely on the supervised model maximises PR-AUC on the four typologies it
trained on and is measurably worse at the two it has never seen. Anyone can pick weights;
the claim worth making is that we measured the curve and chose a point on it.

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

Metrics are chosen for a 3.3% positive rate. **Accuracy never judges this system**, and
where it is reported it is always beside its own baseline — see below for why.

### Entity-level (test fold: n=14,083, 463 positives, base rate 0.0329)

| Metric | Value |
|---|---|
| **PR-AUC** | **0.4635** — 14.1× the 0.0329 base rate |
| Precision @ 10 | 1.00 |
| Precision @ 50 | 0.94 |
| Recall @ precision 0.80 | 0.194 |
| **Expected calibration error** | **0.0494** (target < 0.05) |
| F1 | 0.5380 |
| **MCC** | **0.5359** — the honest single figure under imbalance |
| Accuracy | 0.9745 — **against an all-negative baseline of 0.9671** |

**On accuracy.** A model predicting "everything licit" scores 0.9671 here. Ours scores
0.9745. On the held-out-typology fold accuracy actually falls *below* its own baseline.
That is the entire argument for why this project reports PR-AUC and MCC and treats
accuracy as an artefact to be shown with its control attached.

**On Precision@10.** It reads 1.00, and it is the least reliable number on this page: a
bootstrap over the test fold puts its 95% interval at roughly ±0.30, because it is
computed over ten items. **P@50 = 0.94 is the honest headline.**

### Generalisation to typologies never trained on

71 held-out entities, scored against the test fold's negatives (base rate 0.0052):
**PR-AUC 0.0788, recall at operating threshold 0.1972.**

Materially worse than the test score. **That gap is the finding** — it is the honest
bound on how the system behaves against a laundering pattern nobody anticipated.

### Transaction-level (§16.4-G)

137,273 transactions, 1,929 illicit. **PR-AUC 0.0961 against a 0.0121 base rate — 7.9×.**
P@50 0.40. A second model head over transaction-local features plus the parent entity's
score, split by the parent's fold so no entity straddles the boundary.

### Attribution — the differentiator, measured

| Metric | Value |
|---|---|
| **Top-1 accuracy** | **0.9133** |
| Random-choice baseline | 0.3449 (mean 3.58 candidates) |
| Top-3 accuracy | 0.9142 |
| MRR | 0.9138 |
| Attempt rate | 98.6% |
| Abstentions | 195 — shared infrastructure, correctly declined |

A top-1 score is meaningless without knowing how many candidates it was chosen from, so
the candidate count and the chance baseline ship with it. The engine is **2.6× chance**.

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
among them confidently. That crossing point is a real limit of the method, it is measured
rather than argued, and it is left visible in the Model panel.

### Failure gallery

Three false positives (two `transient` licit pass-through wallets, one `retail`) and three
false negatives (two mules, one extortion actor). The transient false positives are the
informative ones: legitimate short-lived pass-through wallets are structurally
near-identical to laundering mules, and separating them needs counterparty reputation this
system deliberately does not model.

## 7. Limitations

The section most teams omit and an NTRO reader will respect most.

- **Every synthetic figure is self-referential.** We wrote the generator. The leak test
  bounds this — 1.242× against 10.068× — it does not eliminate it.
- **Generator parameters are engineering defaults, not literature-sourced values.** See
  `docs/generator_parameters.md`. Until they are sourced, the defensible claim is about
  the *method and system*, not the absolute detection rate.
- **Class balance is higher than a real base rate**: 3.3% in the test fold, and it drifts
  across folds (train 8.8%, calib 11.6%) because laundering campaigns cluster in time
  and the split is temporally forward.
- **Precision@10's confidence interval is wide.** Quote P@50.
- **Entity resolution is high-precision, moderate-recall.** Purity 0.9958, but receive-only
  addresses fragment into singletons — correct behaviour for these heuristics, and it
  means the entity count far exceeds the true actor count.
- **Attribution degrades with coverage and inverts below ~10%.** See the curve above.
- **Single observations cannot support confident attribution, by design.** Bitcoin Core's
  randomised per-peer relay delay exists precisely to defeat first-relay inference
  (Koshy FC'14, Biryukov CCS'14; Dandelion++ BIP-156 proposed, never merged). We model the
  defence rather than ignoring it.
- **No validation on real labelled data yet.** The Elliptic harness exists
  (`make validate-external`) and reports `available: false` until the dataset is placed in
  `data/external/elliptic/`. Chain-side parity with published baselines is therefore
  claimed as *reproducible*, not as *achieved*.

## 8. Reproduction

```bash
make reproduce      # generate → leak-test → train → score, from a fixed seed
make verify-all     # every check a judge could run
```

Three artefact files carry every number: `metrics.json`, `leak_test.json`,
`manifest.json`. The manifest records the input's SHA-256 (`f090a003…`), the seed
(20260826), the feature version (7), the model backend and the git SHA.

The feature matrix is byte-reproducible from seed, enforced by a golden-file test. That
test found a real defect: `active_entities` returned Polars `group_by` order, which is
non-deterministic, so igraph vertex indices moved between runs and betweenness sampled
different pivots — **fixed-seed runs were producing different feature matrices**. Nothing
but a golden file would have caught it.
