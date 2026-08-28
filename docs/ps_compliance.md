# PS 26146 compliance matrix

One row per requirement, quoting the PS's own wording, with the command that verifies it.
Run `make verify-all` to execute the machine-checkable subset in one pass.

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
| 14 | minimum fields incl. `geo_country/asn` | `generator/emit.py:FIELDS` | 14/14 present | ✅ |
| 15 | "integrate open source downloadable Geo IP database" | `ingest/enrich.py` | **DB-IP Lite ASN, CC BY 4.0**, bundled at `data/geo/dbip-asn-lite.mmdb`; receipt reads `mmdb:dbip-asn-lite.mmdb+table:asn-blocks.csv` | ✅ |

## Expected solution

| # | PS wording | Implemented in | Verified by | Status |
|---|---|---|---|---|
| 16 | "Workable complete offline solution for **linux platform**" | `Dockerfile`, `wheels/` | 62 Linux wheels vendored, no network fallback in the image; `make docker-verify` | ⚠ **build not yet executed — see below** |
| 17 | "Working prototype (**code repo**) with ingestion, correlation, and AI/ML model" | git repo, 75 tests | `make test` → 75 passed | ✅ |
| 18 | "Short technical write-up: approach, model choice, and explainability method" | `docs/technical_writeup.md` | §2 approach, §4 model choice, §5 explainability | ✅ |
| 19 | "Dashboard/visualization showing flagged entities **and evidence for each flag**" | `ui/src/components/CaseFile.tsx` | evidence chain with real TXIDs, SHAP, graph, timeline, attribution | ✅ |

## Outstanding

**Requirement 16 — Linux verification.** All the machinery exists: `wheels/` holds 62
manylinux wheels, the Dockerfile installs `--no-index` with **no network fallback** (a
missing wheel fails the build loudly rather than silently reaching out), and
`scripts/verify_offline.sh` runs the tests, the GeoIP lookup and the full pipeline under
`--network none`.

It has **not been executed**: the Docker daemon would not start on the development
machine. To close this row:

```bash
open -a Docker          # wait for the whale icon to settle
make docker-build
make docker-verify
```

`docker-verify` also reports which ML backend Linux resolves — expected `lightgbm` there,
versus the scikit-learn HistGradientBoosting fallback on macOS hosts without `libomp`.
Artefacts trained on macOS record `sklearn_histgb` in the manifest; retrain inside the
container to ship LightGBM-backed artefacts.
