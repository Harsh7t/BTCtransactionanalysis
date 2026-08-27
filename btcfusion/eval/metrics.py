"""Evaluation metrics chosen for a 2-13% positive rate.

Choosing the metric IS a differentiator here, because the obvious one is
worthless: at a 2% positive rate a model that predicts "all licit" scores 98%
accuracy. Accuracy never appears in this file.

  * PR-AUC is the primary. ROC-AUC is misleadingly flattering under heavy class
    imbalance because the huge negative class makes the false-positive rate look
    tiny no matter what.
  * PRECISION@k is the metric the JOB has. An analyst opens the top ten. If eight
    are real, the tool works. Everything else is commentary.
  * EXPECTED CALIBRATION ERROR decides whether "0.87" is a claim or a decoration.
  * HELD-OUT-TYPOLOGY RECALL measures generalisation to laundering patterns never
    trained on. It will be low. Reporting it anyway is the point.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def pr_auc(y: np.ndarray, s: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, s))


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, s))


def precision_at_k(y: np.ndarray, s: np.ndarray, k: int) -> float:
    """What fraction of the top k are genuinely illicit."""
    if len(y) == 0:
        return float("nan")
    k = min(k, len(y))
    top = np.argsort(-s)[:k]
    return float(y[top].mean())


def recall_at_precision(y: np.ndarray, s: np.ndarray, target: float = 0.8) -> float:
    """How much illicit activity we catch at an acceptable false-alarm rate."""
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s)
    ys = y[order]
    tp = np.cumsum(ys)
    prec = tp / np.arange(1, len(ys) + 1)
    ok = prec >= target
    if not ok.any():
        return 0.0
    return float(tp[ok].max() / y.sum())


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Weighted mean gap between predicted probability and observed frequency."""
    if len(y) == 0:
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        ece += (m.mean()) * abs(p[m].mean() - y[m].mean())
    return float(ece)


def reliability_curve(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    """Points for the reliability diagram in the model panel."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        out.append({"bin": b, "predicted": round(float(p[m].mean()), 4),
                    "observed": round(float(y[m].mean()), 4), "n": int(m.sum())})
    return out


def held_out_recall(y: np.ndarray, s: np.ndarray, threshold: float) -> float:
    """Recall on typologies the model never saw, at the operating threshold."""
    if len(y) == 0 or y.sum() == 0:
        return float("nan")
    return float(((s >= threshold) & (y == 1)).sum() / y.sum())


def evaluate(y: np.ndarray, s: np.ndarray, threshold: float = 0.5) -> dict:
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    return {
        "n": int(len(y)),
        "n_positive": int(y.sum()),
        "positive_rate": round(float(y.mean()) if len(y) else 0.0, 4),
        "pr_auc": round(pr_auc(y, s), 4),
        "roc_auc": round(roc_auc(y, s), 4),
        "precision_at_10": round(precision_at_k(y, s, 10), 4),
        "precision_at_25": round(precision_at_k(y, s, 25), 4),
        "precision_at_50": round(precision_at_k(y, s, 50), 4),
        "recall_at_precision_80": round(recall_at_precision(y, s, 0.8), 4),
        "ece": round(expected_calibration_error(y, s), 4),
        "baseline_pr_auc": round(float(y.mean()) if len(y) else 0.0, 4),
    }


def attribution_metrics(pred: dict, truth_ips: dict[str, set[str]]) -> dict:
    """Top-1 / top-3 accuracy and MRR for entity -> IP attribution.

    Measured only over entities we actually attempted, and the attempt rate is
    reported alongside: a system that answers rarely but correctly and one that
    answers always and often wrongly must not produce the same number.
    """
    attempted = ranks = 0
    top1 = top3 = 0
    rr = 0.0
    for eid, attribution in pred.items():
        truth = truth_ips.get(eid)
        if not truth or not attribution.candidates:
            continue
        attempted += 1
        ips = [c["ip"] for c in attribution.candidates]
        hit = next((i for i, ip in enumerate(ips) if ip in truth), None)
        if hit is None:
            continue
        ranks += 1
        rr += 1.0 / (hit + 1)
        if hit == 0:
            top1 += 1
        if hit < 3:
            top3 += 1
    return {
        "n_attempted": attempted,
        "n_evaluable": len(truth_ips),
        "attempt_rate": round(attempted / max(1, len(truth_ips)), 4),
        "top1_accuracy": round(top1 / max(1, attempted), 4),
        "top3_accuracy": round(top3 / max(1, attempted), 4),
        "mrr": round(rr / max(1, attempted), 4),
    }
