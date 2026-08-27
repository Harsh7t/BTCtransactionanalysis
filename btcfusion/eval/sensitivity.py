"""How much does attribution degrade as we see less of the network?

THIS IS THE HONEST SLIDE. Bitcoin Core's randomised per-peer relay delay already
weakens first-relay attribution; a collector that monitors only part of the P2P
network weakens it further, because the originator's own announcement is often
simply absent from the capture. Every team that touches this will quote one
accuracy number at one implied coverage. Publishing the curve - and saying which
point on it a real vantage point sits at - is the difference.

Each coverage point regenerates the capture from the SAME seed with only
`network.observation_coverage` changed, so the chain layer is identical and the
only thing that varies is how much of the network we watched.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import polars as pl

DEFAULT_COVERAGES = [0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.00]


def sweep_coverage(coverages: list[float] | None = None, seed: int | None = None,
                   n_entities: int | None = None, days: int | None = None,
                   max_entities: int = 4000) -> list[dict]:
    """Attribution accuracy at each observation-coverage level."""
    from ..attribute.engine import attribute
    from ..generator.emit import write_csv, write_truth
    from ..generator.simulate import simulate
    from ..pipeline import load_cfg, prepare
    from .attribution_eval import evaluate_attribution
    from .labels import map_to_truth

    gcfg = load_cfg("generator.yaml")
    dcfg = load_cfg("detect.yaml")
    if n_entities:
        gcfg["population"]["n_entities"] = n_entities
    if days:
        gcfg["time"]["days"] = days
    coverages = coverages or DEFAULT_COVERAGES
    base_seed = seed if seed is not None else int(gcfg["seed"])

    out: list[dict] = []
    for cov in coverages:
        cfg = json.loads(json.dumps(gcfg))          # deep copy
        cfg["network"]["observation_coverage"] = float(cov)
        cap = simulate(cfg, seed=base_seed)

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_path = write_csv(cap.rows, tmp / "capture.csv")
            write_truth(cap, tmp / "truth")
            geo = tmp / "truth" / "geoip_table.csv"

            prep = prepare(csv_path, detect_cfg=dcfg, geo_table=geo)
            truth_ent = pl.read_csv(tmp / "truth" / "truth_entities.csv")
            labels, _ = map_to_truth(
                prep.addr_map,
                pl.read_csv(tmp / "truth" / "truth_addresses.csv"),
                truth_ent)
            acfg = dcfg["attribution"]
            attributions, _ = attribute(
                prep.df, prep.txs, prep.addr_map, prep.nodes[:max_entities],
                alpha=float(acfg["fdr_alpha"]),
                min_count=int(acfg["min_observations"]),
                top_k=int(acfg["top_k_candidates"]))
            got = evaluate_attribution(attributions, truth_ent, labels)
        out.append({"coverage": float(cov),
                    **{k: got[k] for k in ("top1_accuracy", "top3_accuracy", "mrr",
                                           "attempt_rate", "n_evaluable",
                                           "random_choice_baseline", "mean_candidates")}})
    return out


def write_sensitivity(path: Path, rows: list[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "curve": rows,
        "note": ("Attribution accuracy as a function of how much of the P2P network the "
                 "collector observes. The chain layer is identical at every point - only "
                 "observation coverage changes. Reported because first-relay attribution "
                 "is contested and Bitcoin Core actively defends against it; a single "
                 "accuracy number at an unstated coverage would be an overclaim."),
    }, indent=2))
    return path
