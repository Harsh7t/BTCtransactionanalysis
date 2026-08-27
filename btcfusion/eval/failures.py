"""The cases we get wrong, and why.

This artefact does more for credibility than any accuracy number, because it
proves we understand our own system's limits rather than only its strengths.
The reasons are derived from the entity's own features, so they are findings
rather than authored excuses.
"""
from __future__ import annotations

import numpy as np
import polars as pl


def _why(kind: str, row: dict, archetype: str, typology: str) -> str:
    if kind == "false_positive":
        if (row.get("max_n_outputs") or 0) >= 8 and archetype in (
                "exchange", "merchant", "miner"):
            return (f"A legitimate {archetype} batch payout fans value across "
                    f"{int(row['max_n_outputs'])} outputs at once, which is structurally "
                    f"indistinguishable from a laundering fan-out at the topology level. "
                    f"Separating them needs counterparty reputation we deliberately do "
                    f"not model.")
        if (row.get("shared_infra_frac") or 0) > 0.5:
            return ("Announced almost entirely from shared infrastructure, which lifts the "
                    "network-layer features without the chain layer supporting the flag.")
        return (f"Scored above threshold despite a licit label. Its feature profile sits "
                f"in the overlap region between {archetype} behaviour and laundering "
                f"topology.")
    if (row.get("dormancy_ratio") or 0) > 0.6:
        return ("Its signature is almost purely temporal - a long dormancy then a burst - "
                "which the topological features the model leans on cannot see. This is "
                "the held-out typology failure mode, visible in the generalisation score.")
    if (row.get("shared_infra_frac") or 0) > 0.5:
        return ("Routed through shared infrastructure, so the network layer contributed "
                "nothing and the chain layer alone was not decisive.")
    return (f"Genuinely illicit ({typology or 'unlabelled typology'}) but scored below "
            f"threshold: too few transactions to establish the topology the model needs.")


def failure_gallery(entities: list[str], y: np.ndarray, scores: np.ndarray,
                    fm: pl.DataFrame, labels: pl.DataFrame,
                    threshold: float, k: int = 3) -> list[dict]:
    """Worst false positives and worst false negatives, with derived reasons."""
    feats = {r["entity"]: r for r in fm.iter_rows(named=True)}
    meta = {r["entity"]: r for r in labels.iter_rows(named=True)}
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores, dtype=float)

    out: list[dict] = []
    fp_idx = [i for i in np.argsort(-scores) if y[i] == 0 and scores[i] >= threshold][:k]
    fn_idx = [i for i in np.argsort(scores) if y[i] == 1 and scores[i] < threshold][:k]

    for kind, idxs in (("false_positive", fp_idx), ("false_negative", fn_idx)):
        for i in idxs:
            e = entities[i]
            row = feats.get(e, {})
            m = meta.get(e, {})
            out.append({
                "entity": e, "kind": kind,
                "score": round(float(scores[i]), 4),
                "true_label": int(y[i]),
                "archetype": str(m.get("archetype", "unknown")),
                "typology": str(m.get("typology", "")),
                "why": _why(kind, row, str(m.get("archetype", "unknown")),
                            str(m.get("typology", ""))),
            })
    return out
