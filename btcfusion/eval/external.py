"""Validate the chain-side detector on REAL labelled Bitcoin data.

WHY THIS EXISTS. Every other number in this project is measured against a
generator we wrote ourselves, which makes it self-referential. The Elliptic
dataset (Weber et al., 2019) is real, public and hand-labelled, so a competitive
score on it is evidence our modelling approach works on actual Bitcoin rather
than on our own assumptions.

WHAT IT DOES NOT VALIDATE, and we say so on the slide: Elliptic has no IP layer,
no ports, no timing - 166 anonymised, publisher-aggregated features and nothing
else. It cannot exercise the network-chain correlation that is this project's
whole thesis. It validates the CHAIN-SIDE DETECTOR ONLY. That division is the
dual-track strategy, not a hedge.

The files are not committed - licence and size - so every path degrades cleanly
when they are absent, and an absent dataset reports `available: False` rather
than a score computed on nothing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Weber et al. (2019) report Random Forest illicit-class F1 around 0.79 on the
# full feature set, and notably found tree ensembles OUTPERFORMED a GCN. Verify
# this from the paper yourself before putting it on a slide.
PUBLISHED_REFERENCE = {
    "source": "Weber et al. 2019, Anti-Money Laundering in Bitcoin",
    "model": "Random Forest, all features",
    "illicit_f1": 0.79,
    "caveat": "Confirm from the paper before citing. Splits and feature subsets differ.",
}

FEATURES_FILE = "elliptic_txs_features.csv"
CLASSES_FILE = "elliptic_txs_classes.csv"


def _root_ok(root: Path) -> bool:
    return (root / FEATURES_FILE).exists() and (root / CLASSES_FILE).exists()


def load_elliptic(root: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (X, y, feature_names) over LABELLED nodes only.

    Elliptic encodes class as '1' = illicit, '2' = licit, 'unknown' = unlabelled.
    Roughly 77% of nodes are unlabelled and are dropped: treating them as
    negatives would silently mislabel a large illicit population.
    """
    import pandas as pd

    root = Path(root)
    feats = pd.read_csv(root / FEATURES_FILE, header=None)
    classes = pd.read_csv(root / CLASSES_FILE)
    feats = feats.rename(columns={0: "txId", 1: "time_step"})
    classes.columns = [str(c) for c in classes.columns]
    id_col = "txId" if "txId" in classes.columns else classes.columns[0]
    cls_col = "class" if "class" in classes.columns else classes.columns[-1]
    classes = classes.rename(columns={id_col: "txId", cls_col: "class"})
    merged = feats.merge(classes, on="txId", how="inner")
    merged = merged[merged["class"].astype(str).isin(["1", "2"])]

    y = (merged["class"].astype(str) == "1").astype(int).to_numpy()
    drop = [c for c in ("txId", "class") if c in merged.columns]
    body = merged.drop(columns=drop)
    X = body.to_numpy(dtype=np.float32)
    names = [str(c) for c in body.columns]
    return X, y, names


def validate_elliptic(root: Path, seed: int = 20260826) -> dict:
    """Fit our detector on Elliptic and report against published baselines."""
    from ..detect.supervised import SupervisedDetector
    from . import metrics as M

    root = Path(root)
    if not _root_ok(root):
        return {
            "available": False,
            "pr_auc": None,
            "note": ("Elliptic dataset not present. Download elliptic_txs_features.csv "
                     "and elliptic_txs_classes.csv from the Elliptic Data Set on Kaggle "
                     f"into {root}/ and re-run `make validate-external`. Not committed "
                     "for licence and size reasons."),
            "published_reference": PUBLISHED_REFERENCE,
        }

    X, y, names = load_elliptic(root)
    # Temporal split on Elliptic's own time_step, mirroring the discipline used
    # on our synthetic data: predict later activity from earlier.
    ts_col = names.index("time_step") if "time_step" in names else 0
    order = np.argsort(X[:, ts_col])
    cut = int(len(order) * 0.7)
    tr, te = order[:cut], order[cut:]

    model = SupervisedDetector(seed=seed).fit(X[tr], y[tr], names, n_estimators=300)
    s = model.predict_proba(X[te])
    base = M.evaluate(y[te], s, 0.5)
    cls = M.classification_report_at(y[te], s, 0.5)

    return {
        "available": True,
        "n_nodes": int(len(y)),
        "n_labelled": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "n_train": int(len(tr)), "n_test": int(len(te)),
        "pr_auc": base["pr_auc"],
        "precision": cls["precision"], "recall": cls["recall"], "f1": cls["f1"],
        "mcc": cls["mcc"],
        "published_reference": PUBLISHED_REFERENCE,
        "note": ("Chain-side detector only. Elliptic has no IP, port or timing layer, so "
                 "it cannot exercise the network-chain correlation this project is built "
                 "around - that half is validated on synthetic data whose parameters are "
                 "documented in docs/generator_parameters.md. Split is temporally forward "
                 "on Elliptic's own time_step."),
    }
