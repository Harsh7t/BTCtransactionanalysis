"""Positive-Unlabelled learning: use the data everyone else throws away.

THE PROBLEM THIS EXISTS FOR. In anti-money-laundering you never have complete
negatives. You have a set of actors somebody investigated and confirmed, and a
much larger set nobody has looked at - which is not the same as a set of
confirmed-clean actors. Training a classifier on "labelled illicit vs everything
else" teaches it that every uninvestigated actor is innocent, which is exactly
backwards: the ones that matter most are the ones nobody has looked at yet.

The Elliptic benchmark makes the cost visible. It labels 4,545 illicit and 42,019
licit transactions - and leaves 157,205 UNKNOWN. Our own external validation
drops them (eval/external.py), as does most published work on the set, because
the alternative of calling them licit is worse. That is 77% of a real, expensive,
hand-collected dataset discarded for want of a method.

THE METHOD. Elkan and Noto (KDD 2008) show that under the SCAR assumption -
labelled positives are Selected Completely At Random from all positives - a
classifier g(x) trained to separate LABELLED from UNLABELLED is a constant
multiple of the true posterior:

    g(x) = P(labelled | x) = c * P(illicit | x),    c = P(labelled | illicit)

so P(illicit | x) = g(x) / c, and c is estimable as the mean of g over held-out
labelled positives. Two things follow. The correction is monotone, so on its own
it changes calibration and not ranking. What changes the RANKING is using the
estimate to weight the unlabelled examples during a second fit: each unlabelled
point enters twice, as a positive with weight w(x) = (1-c)/c * g(x)/(1-g(x)) and
as a negative with weight 1 - w(x). That fit has seen the 77%.

WHAT WE DO NOT CLAIM. SCAR is an assumption, and on Elliptic it is questionable -
the labelled illicit set came from investigations, which do not sample uniformly.
The correction is therefore reported BESIDE the drop-the-unknowns baseline rather
than replacing it, and the comparison is the finding. On our synthetic data it is
not used at all: the generator knows every label, so c = 1 by construction and a
PU correction there would be theatre.
"""
from __future__ import annotations

import numpy as np

from .supervised import SupervisedDetector


def estimate_c(g_held: np.ndarray) -> float:
    """P(labelled | illicit), as the mean classifier output on held-out positives.

    Elkan & Noto's estimator e1. Clipped away from zero because the weights below
    divide by it, and a c near zero means the labelled set is too small to support
    the correction at all - which the caller should see as a wide weight, not as
    an exception.
    """
    if len(g_held) == 0:
        return 1.0
    return float(np.clip(np.mean(g_held), 1e-3, 1.0))


def pu_weights(g_unlabelled: np.ndarray, c: float) -> np.ndarray:
    """Probability that each unlabelled example is actually positive."""
    g = np.clip(g_unlabelled / c, 0.0, 1.0)
    # w = P(y=1 | x, s=0): the posterior restricted to the unlabelled pool.
    denom = np.clip(1.0 - g * c, 1e-9, None)
    return np.clip(g * (1.0 - c) / denom, 0.0, 1.0)


class PUDetector:
    """Two-stage Elkan-Noto, wrapping the same tree ensemble the rest of the
    system uses, so SHAP, calibration and the narrative layer are unchanged."""

    def __init__(self, seed: int = 20260826, backend: str = "auto"):
        self.seed = seed
        self.backend = backend
        self.c = 1.0
        self.model: SupervisedDetector | None = None

    def fit(self, X_labelled_pos: np.ndarray, X_unlabelled: np.ndarray,
            feature_names: list[str], n_estimators: int = 300,
            holdout: float = 0.25) -> "PUDetector":
        rng = np.random.default_rng(self.seed)
        n_pos = len(X_labelled_pos)
        if n_pos < 20 or len(X_unlabelled) < 20:
            raise ValueError("too few examples to estimate c")

        # Stage 1: labelled-vs-unlabelled, with a slice of the positives held
        # back. Estimating c on positives the stage-1 model trained on would
        # measure how well it memorised them, not how often a positive gets
        # labelled.
        perm = rng.permutation(n_pos)
        n_hold = max(10, int(n_pos * holdout))
        hold, keep = perm[:n_hold], perm[n_hold:]

        Xs = np.vstack([X_labelled_pos[keep], X_unlabelled])
        s = np.concatenate([np.ones(len(keep), dtype=np.int8),
                            np.zeros(len(X_unlabelled), dtype=np.int8)])
        stage1 = SupervisedDetector(seed=self.seed, backend=self.backend).fit(
            Xs, s, feature_names, n_estimators=n_estimators)
        self.c = estimate_c(stage1.predict_proba(X_labelled_pos[hold]))

        # Stage 2: every unlabelled point enters as both classes, weighted by how
        # likely it is to be positive. This is the step that lets the 77% move
        # the decision boundary instead of sitting outside the problem.
        w_pos = pu_weights(stage1.predict_proba(X_unlabelled), self.c)
        X2 = np.vstack([X_labelled_pos, X_unlabelled, X_unlabelled])
        y2 = np.concatenate([np.ones(n_pos, dtype=np.int8),
                             np.ones(len(X_unlabelled), dtype=np.int8),
                             np.zeros(len(X_unlabelled), dtype=np.int8)])
        w2 = np.concatenate([np.ones(n_pos), w_pos, 1.0 - w_pos])

        self.model = SupervisedDetector(seed=self.seed, backend=self.backend)
        self.model.fit_weighted(X2, y2, w2, feature_names, n_estimators=n_estimators)
        self.feature_names = list(feature_names)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        assert self.model is not None, "fit first"
        return self.model.predict_proba(X)
