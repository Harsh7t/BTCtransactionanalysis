"""Elliptic++ actor-level validation.

The dataset cannot be committed (1.3 GB, no upstream licence), so every path has
to work without it - and must never report a score computed on nothing.

The traps these tests pin down are the ones that would silently INFLATE the
result: an address appearing in both train and test, and a pair-weighted
agreement metric dominated by a single supercluster.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from btcfusion.eval.elliptic_pp import (
    ILLICIT, LICIT, UNKNOWN, load_wallets, validate_elliptic_pp)


def _fixture(tmp_path: Path) -> Path:
    """Elliptic++'s real file names, column names and label encoding."""
    root = tmp_path / "elliptic_pp"
    root.mkdir()
    rng = np.random.default_rng(0)
    rows = []
    for a in range(300):
        # addresses recur across time steps - the leakage trap this guards
        for step in ([3, 40] if a % 5 == 0 else [rng.integers(1, 50)]):
            cls = ILLICIT if a % 7 == 0 else (LICIT if a % 3 else UNKNOWN)
            rows.append({"address": f"addr{a}", "Time step": int(step), "class": cls,
                         **{f"f{i}": float(rng.normal()) for i in range(6)}})
    pd.DataFrame(rows).to_csv(root / "wallets_features_classes_combined.csv", index=False)

    edges = [{"input_address": f"addr{a}", "txId": t}
             for t in range(120) for a in rng.choice(300, 3, replace=False)]
    pd.DataFrame(edges).to_csv(root / "AddrTx_edgelist.csv", index=False)
    return root


def test_absent_dataset_reports_unavailable_not_a_fake_score(tmp_path):
    got = validate_elliptic_pp(tmp_path, seed=1)
    assert got["available"] is False
    assert "wallet_classification" not in got
    assert "download" in got["note"].lower()


def test_loader_drops_unknown_and_maps_illicit_to_one(tmp_path):
    """Elliptic++ wallets encode unknown as the INTEGER 3, not the string the
    transaction files use. Treating unknowns as licit would mislabel a large
    illicit population."""
    df = load_wallets(_fixture(tmp_path))
    assert UNKNOWN not in df.get_column("class").to_list()
    assert set(df.get_column("y").to_list()) == {0, 1}
    illicit = df.filter(df.get_column("class") == ILLICIT)
    assert illicit.get_column("y").to_list() == [1] * illicit.height


def test_test_addresses_never_appear_in_training(tmp_path):
    """The headline split must be address-disjoint. An address active in two time
    steps otherwise lands on both sides with the same label, and the model scores
    it by memorised identity rather than by behaviour."""
    got = validate_elliptic_pp(_fixture(tmp_path), seed=1)["wallet_classification"]
    assert got["n_test_addresses_dropped_as_seen_in_train"] > 0, "fixture must exercise it"
    assert got["train_steps"][1] < got["test_steps"][0]
    assert got["headline_address_disjoint"]["n"] < got["naive_repeated_addresses"]["n"]


def test_agreement_is_reported_three_ways_against_a_shuffle_control(tmp_path):
    """A pair-weighted agreement is dominated by the largest cluster, so the
    macro and excluding-largest views have to be there to show the skew."""
    got = validate_elliptic_pp(_fixture(tmp_path), seed=1)["cospend_clustering"]
    obs, ctrl = got["label_agreement"], got["label_agreement_shuffled_control"]
    for k in ("micro", "macro", "micro_excl_largest"):
        assert obs[k] is None or 0.0 <= obs[k] <= 1.0
        assert 0.0 <= ctrl[k] <= 1.0
    assert got["cluster_sizes_labelled"]["max"] >= 1


def test_shuffle_control_destroys_the_signal_on_planted_clusters(tmp_path):
    """The control has to be a real control: on clusters built so that every
    member shares a label, observed agreement must beat the shuffle. If this
    passes on random data too, the metric is measuring nothing."""
    root = tmp_path / "pp"
    root.mkdir()
    rows, edges = [], []
    for c in range(40):                       # 40 clusters of 4, label by cluster
        cls = ILLICIT if c % 2 else LICIT
        for k in range(4):
            a = f"addr{c}_{k}"
            rows.append({"address": a, "Time step": 1 + (c % 49), "class": cls,
                         **{f"f{i}": float(c + k) for i in range(4)}})
            edges.append({"input_address": a, "txId": c})   # co-spent together
    pd.DataFrame(rows).to_csv(root / "wallets_features_classes_combined.csv", index=False)
    pd.DataFrame(edges).to_csv(root / "AddrTx_edgelist.csv", index=False)

    got = validate_elliptic_pp(root, seed=1)["cospend_clustering"]
    assert got["label_agreement"]["macro"] == pytest.approx(1.0), "planted clusters are pure"
    assert got["label_agreement"]["macro"] > got["label_agreement_shuffled_control"]["macro"]
    assert got["lift_macro"] > 1.0
