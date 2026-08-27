"""Golden-file test: a fixed seed must produce a byte-identical feature matrix.

This is the tripwire for silent numerical drift. A refactor that changes a
feature's value by 1e-6 changes every downstream number while every unit test
still passes; this catches it on the next run.

Regenerate deliberately with `make golden-update` and READ THE DIFF - an
unexplained change to the golden file is a bug report, not a chore.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden" / "feature_matrix.json"


def _fingerprint(tmp_path: Path) -> dict:
    from btcfusion.generator.emit import write_csv, write_truth
    from btcfusion.generator.simulate import simulate
    from btcfusion.pipeline import load_cfg, prepare

    cfg = load_cfg("generator.yaml")
    cfg["population"]["n_entities"] = 100
    cfg["time"]["days"] = 6
    cfg["typologies"]["n_campaigns"] = 4
    cfg["typologies"]["n_licit_passthrough"] = 10
    cap = simulate(cfg, seed=424242)
    csv = write_csv(cap.rows, tmp_path / "golden.csv")
    write_truth(cap, tmp_path / "truth")

    prep = prepare(csv, detect_cfg=load_cfg("detect.yaml"),
                   geo_table=tmp_path / "truth" / "geoip_table.csv")
    fm = prep.fm.sort("entity")
    names = [c for c in fm.columns if c != "entity"]
    # Hash the numeric block at fixed precision: exact float equality across
    # platforms is not a promise anyone can keep; six decimals is.
    body = "\n".join(",".join(f"{v:.6f}" for v in row) for row in fm.select(names).rows())
    return {
        "n_entities": fm.height,
        "feature_names": names,
        "matrix_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


@pytest.mark.skipif(not GOLDEN.exists(),
                    reason="no golden file yet; run `make golden-update`")
def test_feature_matrix_is_unchanged(tmp_path):
    got = _fingerprint(tmp_path)
    want = json.loads(GOLDEN.read_text())
    assert got["feature_names"] == want["feature_names"], (
        "The feature SET changed. If intentional, run `make golden-update` and note it "
        "in the commit - every previously recorded metric is now incomparable.")
    assert got["n_entities"] == want["n_entities"]
    assert got["matrix_sha256"] == want["matrix_sha256"], (
        "Feature VALUES drifted with no feature-set change. This silently moves every "
        "downstream number. Find the cause before regenerating the golden file.")
