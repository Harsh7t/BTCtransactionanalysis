# PS 26146 compliance matrix

One row per requirement, quoting the PS's own wording, with the command that verifies it.
Run `make verify-all` to execute the machine-checkable subset in one pass.

> **PROFILE NOTE.** This matrix quotes the **bulk** profile except where stated, but some
> figures elsewhere come from **demo** and the two do not agree — e.g. 214 behavioural
> archetypes (demo) vs 749 (bulk), and attribution top-1 0.9133 (demo, in
> `attribution_method.md`) vs 0.9321 (bulk, in `artifacts/bulk/manifest.json`). Neither is
> wrong; they are different runs. Say which profile a number came from whenever it is
> quoted, and prefer bulk — it is the realistic base rate.

## Objective

| # | PS wording | Implemented in | Verified by | Status |
|---|---|---|---|---|
| 1 | "complete system (offline)" | whole repo | `make offline-check` → PASS, no runtime host in any application file | ✅ |
| 2 | "ingests bulk Bitcoin transaction/network metadata" | `ingest/parsers.py` | `make run` → 2,467,299 rows in 105 s (bulk); 564,303 in 11.8 s (demo) | ✅ |
| 3 | "in CSV/JSON/XML" | `ingest/parsers.py:READERS` | all three parse to **identical** clean-row counts | ✅ |
| 4 | "correlates network-layer (IP/port/timing) with blockchain-layer (wallet/TXID/amount)" | `attribute/engine.py` | `metrics.json → attribution.top1_accuracy` = **0.9321** vs 0.3378 chance (bulk) | ✅ |
| 5 | "applies AI/ML to detect anomalies" | `detect/supervised.py`, `detect/novelty.py` | test PR-AUC **0.3048** vs 0.0039 base rate on bulk (78×) | ✅ |
| 6 | "cluster entities" | `graph/resolve.py` + `detect/novelty.py` | **two levels**: 829,821 address clusters on bulk (purity 0.9958) and 214 HDBSCAN behavioural archetypes | ✅ |
| 7 | "generate prioritized, explainable investigative leads" | `pipeline.py`, `explain/` | ranked queue, isotonic-calibrated (ECE 0.0405 on bulk), exact SHAP → narrative | ✅ |

## Challenge objectives

| # | PS wording | Implemented in | Verified by | Status |
|---|---|---|---|---|
| 8 | "Ingest & parse a bulk metadata dataset (timestamp, src/dst IP & port, TXID, input/output wallet addresses, amounts, fee, script type)" | `ingest/` | all 14 fields present: `head -1 data/samples/capture.csv` | ✅ |
| 9 | "Build an entity/transaction graph linking **IPs, wallets, and transactions**" | `graph/build.py` | `/api/graph/{e}` (entity layer) + `/api/graph/{e}/expand` (wallet + transaction layers) | ✅ |
| 10 | "Implement AI/ML detection use case with a **working model — not just rules**" | `detect/` | ablation on bulk: rules alone **0.0030** (below the 0.0039 base rate), model **0.3231** | ✅ |
| 11 | "ranked, explainable alert list (why a **wallet/transaction** was flagged, with a confidence score)" | `pipeline.py`, `detect/transaction_head.py` | `/api/alerts` (entity) and `/api/transactions` (TXID, PR-AUC 0.1098 vs 0.0121 base) | ✅ |
| 12 | "Present findings via a simple dashboard or link-analysis visualization" | `ui/` | 4 screens; case file carries evidence with real TXIDs | ✅ |

## Section 4 — Suggested AI/ML Focus Areas

| # | PS wording | Status |
|---|---|---|
| — | *"Attach Table Here of AI/ML Focus Areas"* | ⚠ **Never published by the organisers.** We define the detection scope and say so explicitly — `docs/technical_writeup.md` §1 |

## Dataset

| # | PS wording | Implemented in | Verified by | Status |
|---|---|---|---|---|
| 13 | "synthetic dataset modelled on real Bitcoin P2P/transaction fields" | `generator/` (1,680 lines) | `make generate`; parameters documented in `docs/generator_parameters.md` | ✅ |
| 13b | *beyond the PS* — the synthetic set is ours, so the chain-side detector is also validated on **real** labelled Bitcoin data | `eval/external.py` | `make validate-external` → illicit **F1 0.7595**, PR-AUC 0.8009 on 46,564 Elliptic transactions (train steps 1-34, test 35-49) vs Weber et al.'s published 0.79. Chain-side only — Elliptic has no IP layer | ✅ |
| 13c | *beyond the PS* — and at the **actor level we actually ship**, plus the clustering heuristic itself | `eval/elliptic_pp.py` | `make validate-elliptic-pp` → address PR-AUC **0.3745** at a 5.56% base rate on 96,023 Elliptic++ addresses (address-disjoint split); co-spend clusters share a label **99.79%** vs an 82.09% shuffle control on real Bitcoin | ✅ |
| 14 | minimum fields incl. `geo_country/asn` | `generator/emit.py:FIELDS` | 14/14 present | ✅ |
| 15 | "integrate open source downloadable Geo IP database" | `ingest/enrich.py` | **DB-IP Lite ASN, CC BY 4.0**, bundled at `data/geo/dbip-asn-lite.mmdb`; receipt reads `mmdb:dbip-asn-lite.mmdb+table:asn-blocks.csv` | ✅ |

## Expected solution

| # | PS wording | Implemented in | Verified by | Status |
|---|---|---|---|---|
| 16 | "Workable complete offline solution for **linux platform**" | `Dockerfile`, `wheels/` | **executed**: `make docker-build && make docker-verify` → 5/5 steps pass under `--network none` on linux/amd64. 81 tests, LightGBM 3.3.5 resolved, GeoIP offline, full pipeline on 564k rows, and container scores bit-identical to the host | ✅ |
| 17 | "Working prototype (**code repo**) with ingestion, correlation, and AI/ML model" | git repo, 75 tests | `make test` → 75 passed | ✅ |
| 18 | "Short technical write-up: approach, model choice, and explainability method" | `docs/technical_writeup.md` | §2 approach, §4 model choice, §5 explainability | ✅ |
| 19 | "Dashboard/visualization showing flagged entities **and evidence for each flag**" | `ui/src/components/CaseFile.tsx` | evidence chain with real TXIDs, SHAP, graph, timeline, attribution | ✅ |

## Requirement 16 — what running it actually found

The machinery had existed for days and was described as ready. It was not: the build
failed the first time it was ever run, for two reasons, and both are the kind that only a
real execution exposes.

**No `.dockerignore`.** The Dockerfile `COPY`s only what it needs, but Docker sends the
whole context to the daemon first — 4.6 GB of datasets, a host virtualenv and two
`node_modules` trees. Now 351 MB, nearly all of it the wheels that are actually installed.

**No platform pin.** The vendored wheels are manylinux **x86_64**; on an Apple Silicon host
Docker defaults to an **arm64** base image, so `pip --no-index` found no matching numpy and
the build died at the install step. `PLATFORM ?= linux/amd64` is now pinned in the Makefile
and in `verify_offline.sh`, which also matches the real deployment target.

**A third thing the run surfaced, which is now a permanent check.** The container installs
scikit-learn 1.7.2 while the shipped artefacts were pickled by 1.9.0, and scikit-learn warns
that unpickling across versions "might lead to breaking code or invalid results". We
measured it: the scores are bit-identical, SHA-256
`5eeb9d3f…`. But that is a fact about two specific versions, not a property of the design,
and `vendor_wheels.sh` pins no versions at all — so the next re-vendor could land on a
release where it is no longer true, silently. Step 5/5 of the offline verification now
reproduces the host fingerprint inside the container and **fails the build** if it drifts.

Note that a fresh detector inside the container resolves **LightGBM**, while the shipped
artefacts record `sklearn_histgb` because they were trained on a macOS host without
`libomp`. Both are true and the manifest records which produced every number. To ship
LightGBM-backed artefacts, retrain inside the container.

