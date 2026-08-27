# Reproducing every published number

One command:

```bash
make reproduce
```

Fixed seed in (`config/generator.yaml: seed`), three artefacts out:

| File | Contains |
|---|---|
| `artifacts/v1/metrics.json` | every evaluation figure: PR-AUC, P@k, ECE, reliability curve, ablation, fusion sweep, held-out typology scores, split report, entity-resolution quality |
| `artifacts/v1/leak_test.json` | generator integrity: per-field lift, strict vs informative tiers, the control, and the known residual |
| `artifacts/v1/manifest.json` | input SHA-256, seed, feature version, model backend, git SHA, training row count |

**If a number is not in one of those three files, it is not a result.** Do not put it on
a slide.

## Verifying independently

```bash
make leak-test        # must PASS — gates everything downstream
make test             # 31 tests: resolution correctness, split integrity, attribution math
make offline-check    # fails if any application file references a remote host
```

## What is NOT reproducible from seed

The wall-clock timings shown in the UI and quoted in the README are machine-dependent.
They were measured on an 8-core CPU with no GPU. Re-measure on your own hardware before
quoting them; every other figure is deterministic.

## Before publishing anything

The generator's parameters are engineering defaults chosen to make the two-layer fusion
thesis exercisable, **not** measured values from the literature. Section 6.3 of the
roadmap requires each distribution to name its source before any accuracy claim goes on
a slide. Until that is done, the defensible claim is about the *system* and the
*method* — not the absolute detection rate.
