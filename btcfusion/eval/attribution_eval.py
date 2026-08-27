"""Grade entity -> IP attribution against ground truth.

WHY THIS IS NOT A ONE-LINER. Our resolver rediscovers entities from co-spending,
so its IDs are not the generator's; truth is reached through the label map. And
the metric has to respect ABSTENTION: the engine deliberately suppresses
attribution when every candidate address is shared infrastructure, and a system
that declines to answer must not be scored identically to one that answers
wrongly. So attempt rate is reported alongside accuracy, always.

This module may import ground truth. Nothing under features/, detect/ or
attribute/ may.
"""
from __future__ import annotations

import polars as pl


def evaluate_attribution(attributions: dict, truth_entities: pl.DataFrame,
                         label_map: pl.DataFrame) -> dict:
    """Top-1 / top-3 / MRR over entities we could actually grade.

    attributions: entity -> Attribution (candidates ordered best-first)
    truth_entities: generator ground truth; needs columns `eid` and `ips`
    label_map: resolved `entity` -> `true_eid`, from eval.labels.map_to_truth
    """
    truth_ips: dict[str, set[str]] = {}
    for row in truth_entities.select(["eid", "ips"]).iter_rows(named=True):
        ips = {p for p in str(row["ips"] or "").split("|") if p}
        if ips:
            truth_ips[row["eid"]] = ips

    to_true = dict(zip(label_map.get_column("entity").to_list(),
                       label_map.get_column("true_eid").to_list()))

    evaluable = attempted = top1 = top3 = 0
    abstained = 0
    rr = 0.0
    # Difficulty context. A top-1 score is meaningless without knowing how many
    # candidates it was chosen from: picking the right IP out of one is not an
    # achievement. Recorded so the accuracy figure can never be quoted naked.
    n_candidates: list[int] = []
    for eid, a in attributions.items():
        true_eid = to_true.get(eid)
        truth = truth_ips.get(true_eid) if true_eid else None
        if not truth:
            continue                       # nothing to grade against
        evaluable += 1
        cands = [c["ip"] for c in (a.candidates or [])]
        if not cands:
            # Abstention. Correct abstention is a virtue, not a miss.
            if a.status in ("suppressed", "no_significant_link"):
                abstained += 1
            continue
        attempted += 1
        n_candidates.append(len(cands))
        hit = next((i for i, ip in enumerate(cands) if ip in truth), None)
        if hit is None:
            continue
        rr += 1.0 / (hit + 1)
        if hit == 0:
            top1 += 1
        if hit < 3:
            top3 += 1

    return {
        "n_evaluable": evaluable,
        "n_attempted": attempted,
        "attempt_rate": round(attempted / evaluable, 4) if evaluable else 0.0,
        "top1_accuracy": round(top1 / attempted, 4) if attempted else 0.0,
        "top3_accuracy": round(top3 / attempted, 4) if attempted else 0.0,
        "mrr": round(rr / attempted, 4) if attempted else 0.0,
        "n_abstained": abstained,
        "mean_candidates": round(sum(n_candidates) / len(n_candidates), 3)
        if n_candidates else 0.0,
        "single_candidate_share": round(
            sum(1 for c in n_candidates if c <= 1) / len(n_candidates), 4)
        if n_candidates else 0.0,
        # What a coin flip among the returned candidates would score. The gap
        # between this and top1_accuracy is the engine's actual contribution.
        "random_choice_baseline": round(
            sum(1.0 / c for c in n_candidates) / len(n_candidates), 4)
        if n_candidates else 0.0,
        "note": ("Scored only over entities whose ground truth carries at least one "
                 "announcing IP. Abstentions are excluded from accuracy and reported "
                 "separately: suppressing an attribution that cannot be made honestly "
                 "is correct behaviour, not a miss. Compare top1_accuracy against "
                 "random_choice_baseline: picking correctly from one candidate is not "
                 "a result, and the gap between the two is what the engine contributes."),
    }
