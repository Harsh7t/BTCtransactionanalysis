"""External validation must degrade cleanly when the dataset is absent.

The Elliptic files cannot be committed (licence + size), so every path here has
to work on a machine that does not have them - and must never silently report a
score computed on nothing.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from btcfusion.eval.external import load_elliptic, validate_elliptic


def test_absent_dataset_reports_unavailable_not_a_fake_score(tmp_path):
    got = validate_elliptic(tmp_path, seed=1)
    assert got["available"] is False
    assert got.get("pr_auc") is None
    assert "download" in got["note"].lower()


def _fixture(tmp_path: Path) -> Path:
    """A stand-in with Elliptic's real file names and label encoding."""
    root = tmp_path / "elliptic"
    root.mkdir()
    rng = np.random.default_rng(0)
    n = 400
    feats = pd.DataFrame({0: range(n), 1: rng.integers(1, 40, n)})
    for c in range(2, 12):
        feats[c] = rng.normal(size=n)
    feats.to_csv(root / "elliptic_txs_features.csv", header=False, index=False)
    # Elliptic encodes: 1 = illicit, 2 = licit, unknown = unlabelled
    cls = ["1" if i % 10 == 0 else ("2" if i % 3 else "unknown") for i in range(n)]
    pd.DataFrame({"txId": range(n), "class": cls}).to_csv(
        root / "elliptic_txs_classes.csv", index=False)
    return root


def test_loader_keeps_only_labelled_nodes_and_maps_classes(tmp_path):
    X, y, names = load_elliptic(_fixture(tmp_path))
    assert set(np.unique(y)).issubset({0, 1})
    assert y.sum() > 0, "class '1' must map to illicit=1"
    assert len(names) == X.shape[1]
    assert len(X) == len(y)
    assert len(y) < 400, "unlabelled nodes must be dropped, not treated as licit"


def test_validation_returns_real_metrics_on_the_fixture(tmp_path):
    got = validate_elliptic(_fixture(tmp_path), seed=1)
    assert got["available"] is True
    assert 0.0 <= got["pr_auc"] <= 1.0
    assert got["n_labelled"] > 0


def test_temporal_split_does_not_share_a_time_step(tmp_path):
    """The cut must land on a step boundary.

    A positional 70% cut splits one time step across train and test, which is
    exactly what a temporal split exists to prevent.
    """
    got = validate_elliptic(_fixture(tmp_path), seed=1)
    assert got["train_steps"][1] < got["test_steps"][0]


def test_ablation_refits_without_the_time_index(tmp_path):
    """time_step is both a feature and the split variable, so the claim that the
    score does not rest on it has to be measured, not asserted."""
    got = validate_elliptic(_fixture(tmp_path), seed=1)
    assert 0.0 <= got["without_time_step"]["pr_auc"] <= 1.0
    assert 0.0 <= got["without_time_step"]["f1"] <= 1.0


def test_pu_recovers_a_known_label_frequency():
    """The Elkan-Noto machinery must estimate c correctly on data where we set it.

    Build a separable two-class problem, then HIDE a known fraction of the
    positives in the unlabelled pool. c is the fraction of positives that stayed
    labelled, so the estimator has a right answer to be checked against - which is
    the only way to know the correction means anything before pointing it at
    Elliptic, where the true c is unknowable.
    """
    import numpy as np

    from btcfusion.detect.pu import PUDetector

    rng = np.random.default_rng(7)
    n = 3000
    X_pos = rng.normal(loc=2.0, size=(n, 6))
    X_neg = rng.normal(loc=-2.0, size=(n, 6))

    true_c = 0.6
    n_lab = int(n * true_c)
    labelled_pos = X_pos[:n_lab]
    unlabelled = np.vstack([X_pos[n_lab:], X_neg])   # hidden positives + negatives

    pu = PUDetector(seed=1, backend="sklearn_histgb").fit(
        labelled_pos, unlabelled, [f"f{i}" for i in range(6)], n_estimators=60)

    assert abs(pu.c - true_c) < 0.15, f"estimated c={pu.c:.3f}, expected ~{true_c}"
    # And the corrected model must still separate the classes it was never told about.
    s_pos = pu.predict_proba(X_pos[n_lab:]).mean()
    s_neg = pu.predict_proba(X_neg).mean()
    assert s_pos > s_neg, "PU model does not rank hidden positives above negatives"
