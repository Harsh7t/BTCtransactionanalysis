"""Why the model is worse on the test fold than on the calibration fold.

The splits are temporally forward, and discrimination falls across them - on the
bulk profile ROC-AUC goes 0.996 (train) -> 0.954 (calib) -> 0.674 (test). The
base rate falls 23x over the same stretch, and the reflex is to blame that, but
ROC-AUC is prevalence-independent: it cannot be moved by the positive rate alone.
Something about the late fold is genuinely harder, and "the model degrades over
time" is only one of the explanations.

The other is RIGHT-CENSORING, and it is structural rather than a modelling
failure. A capture ends. An entity that first appears a week before the end has
one week of behaviour in it, however long it actually operated; every aggregate
feature - lifespan, burstiness, transaction count, IP churn - is computed over a
truncated window. A temporally-forward split puts exactly those entities in the
test fold, so the model is being asked to score partial actors and then marked
against ground truth that knows the whole story.

The two explanations imply opposite fixes, so this measures which one it is:
stratify the fold by how much observation window each entity actually had and by
how much activity was seen, and report discrimination inside each stratum. If
censoring is the cause, discrimination recovers on the entities that had a full
window and the deficit concentrates in the thin ones. If it is drift, the deficit
is flat across strata and the model, not the window, is what needs fixing.
"""
from __future__ import annotations

import numpy as np

from . import metrics as M


def _block(y: np.ndarray, s: np.ndarray) -> dict:
    """Discrimination inside one stratum, or nulls where it is undefined."""
    n_pos = int(y.sum())
    if n_pos == 0 or n_pos == len(y):
        return {"n": int(len(y)), "n_positive": n_pos,
                "roc_auc": None, "pr_auc": None,
                "note": "single-class stratum - discrimination undefined"}
    return {"n": int(len(y)), "n_positive": n_pos,
            "positive_rate": round(float(y.mean()), 5),
            "roc_auc": round(M.roc_auc(y, s), 4),
            "pr_auc": round(M.pr_auc(y, s), 4),
            "lift_over_base": round(M.pr_auc(y, s) / max(float(y.mean()), 1e-9), 1)}


def _by_quartile(y: np.ndarray, s: np.ndarray, by: np.ndarray, label: str) -> dict:
    """Split on the quartiles of `by` and report each bucket.

    Quartiles of the observed values, not fixed cut points: the distributions are
    heavy-tailed and any constant would put everything in one bucket on one
    profile and spread it on another.
    """
    edges = np.quantile(by, [0.25, 0.5, 0.75])
    bucket = np.digitize(by, edges)
    out = {}
    for b in range(4):
        m = bucket == b
        if not m.any():
            continue
        lo = by[m].min()
        hi = by[m].max()
        out[f"q{b + 1}"] = {**_block(y[m], s[m]),
                            "range": [round(float(lo), 3), round(float(hi), 3)]}
    return {"stratified_by": label, "buckets": out}


def censoring_report(y: np.ndarray, score: np.ndarray, first_ts: np.ndarray,
                     last_ts: np.ndarray, n_tx: np.ndarray,
                     capture_end: float) -> dict:
    """Is the late-fold deficit censoring, or drift?

    `first_ts` / `last_ts` / `capture_end` are epoch seconds.
    """
    if len(y) == 0 or y.sum() in (0, len(y)):
        return {"available": False,
                "note": "fold is single-class - nothing to stratify"}

    exposure_days = np.clip(capture_end - first_ts, 0, None) / 86400.0
    observed_days = np.clip(last_ts - first_ts, 0, None) / 86400.0
    # An entity whose last transaction lands at the very edge of the capture was
    # still active when the recording stopped; whatever it did next is missing.
    # This is the sharpest single indicator of truncation available without
    # ground truth about the campaign's real end.
    still_active = (capture_end - last_ts) < 86400.0

    overall = _block(y, score)
    complete = _block(y[~still_active], score[~still_active])
    truncated = _block(y[still_active], score[still_active])

    by_exposure = _by_quartile(
        y, score, exposure_days, "days between first activity and end of capture")

    # The finished-vs-truncated split is the weaker test: on a realistic base rate
    # the truncated group can hold too few positives to score at all, which is how
    # this returned "indeterminate" on the bulk profile while its own quartile
    # table ran 0.559 -> 0.767. Read the trend across the exposure quartiles
    # instead - censoring predicts monotone recovery as the window grows, drift
    # predicts a flat deficit - and fall back to the split only if it is unusable.
    aucs = [b["roc_auc"] for b in by_exposure["buckets"].values()
            if b.get("roc_auc") is not None]
    verdict = "indeterminate - too few positives in any stratum to tell"
    if len(aucs) >= 3:
        rising = all(b >= a - 0.02 for a, b in zip(aucs, aucs[1:]))
        spread = aucs[-1] - aucs[0]
        if rising and spread >= 0.05:
            verdict = (f"censoring - discrimination rises monotonically with the "
                       f"observation window, {aucs[0]:.3f} on the shortest quartile "
                       f"to {aucs[-1]:.3f} on the longest. The late fold is not "
                       f"harder because the model has drifted; it is harder because "
                       f"those entities were seen for less time.")
        elif abs(spread) < 0.05:
            verdict = ("drift or intrinsic difficulty - discrimination does not "
                       "depend on the observation window, so truncation does not "
                       "explain the deficit")
        else:
            verdict = ("mixed - the window matters but not monotonically; read the "
                       "strata rather than this summary")

    return {
        "available": True,
        "overall": overall,
        "still_active_at_capture_end": {
            **truncated,
            "definition": "last transaction within 24h of the end of the capture",
        },
        "finished_inside_capture": complete,
        "verdict": verdict,
        "by_exposure_window": by_exposure,
        "by_observed_span": _by_quartile(
            y, score, observed_days, "days between the entity's first and last transaction"),
        "by_activity_volume": _by_quartile(
            y, score, n_tx.astype(float), "transactions sent"),
    }
