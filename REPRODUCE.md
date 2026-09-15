# Reproducing every published number

One command regenerates the demo profile:

```bash
make reproduce        # generate (seeded) → leak test (gate) → train + evaluate → score
```

Fixed seed in (`config/generator.yaml: seed` = 20260826), artefacts out:

| File | Contains |
|---|---|
| `artifacts/v1/metrics.json` | every evaluation figure: PR-AUC, P@k, ECE, reliability curve, ablation, the three queue orderings, fusion sweep, held-out typology scores, censoring strata, split report, entity resolution, attribution accuracy, failure gallery |
| `artifacts/v1/leak_test.json` | generator integrity: per-field lift, strict vs informative tiers, the control, and the known residual |
| `artifacts/v1/manifest.json` | input SHA-256, seed, feature version, model backend, git SHA, training row count |
| `artifacts/v1/sensitivity.json` | attribution accuracy against observation coverage (`make sensitivity`) |
| `artifacts/v1/{external,elliptic_pp}_validation.json` | real-data validation — needs the downloaded datasets (`make validate-external`, `make validate-elliptic-pp`) |

**If a number is not in one of those files, it is not a result.** Do not put it on a slide.

Generation and training are byte-reproducible: two runs from the same seed give identical
data and zero differing metric keys, checked across separate processes by
`tests/test_determinism.py`.

## The bulk profile — the one to quote

`artifacts/bulk/` holds the same files for the 2,467,299-row profile at a realistic 0.39%
base rate. `make reproduce` does not build it: its `generate` step always writes the demo
capture. The bulk equivalent is to generate the bulk capture and point the same targets at
it:

```bash
.venv/bin/python -m btcfusion.cli generate --name bulk --profile bulk --format csv
make leak-test train CAPTURE=data/samples/bulk.csv TRUTH=data/samples/bulk_truth ART=artifacts/bulk
```

The bulk artefacts on disk were trained on 7 September 2026 at git `5a20a09`; the two
commands above describe that path but have not been re-run in exactly this form since.
Training bulk takes about 11 minutes on a laptop CPU.

## Verifying independently

```bash
make leak-test        # must PASS — gates everything downstream
make test             # 88 tests: resolution, splits, attribution maths, calibration, determinism, robustness
make offline-check    # fails if any application file references a remote host
make verify-all       # every host check in one pass
```

## What is NOT reproducible from seed

Wall-clock timings are machine-dependent. The demo profile scores end to end in about 15 s
on an Apple M4 laptop CPU with no GPU; the Provenance screen shows the per-stage timings of
each run. Re-measure on your own hardware before quoting a time — every other figure is
deterministic.

## Before publishing anything

The generator's parameters are engineering defaults chosen to make the two-layer fusion
thesis exercisable, **not** measured values from the literature. Section 6.3 of the
roadmap requires each distribution to name its source before any accuracy claim goes on
a slide. Until that is done, the defensible claim is about the *system* and the
*method* — not the absolute detection rate.
