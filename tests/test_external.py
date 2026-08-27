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
