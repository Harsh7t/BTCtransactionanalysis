"""Map resolved entities onto ground truth.

Our resolver rediscovers entities from co-spending; its IDs are not the
generator's IDs, so grading requires a mapping. A resolved cluster is assigned
the label of the true entity owning the MAJORITY of its addresses, and we record
the purity of that assignment so a contaminated cluster can be excluded rather
than silently mislabelled.

This module is the only place ground truth touches the pipeline, and nothing in
btcfusion.features or btcfusion.detect may import it. Keeping that boundary
sharp is what stops a label leaking into a feature.
"""
from __future__ import annotations

import polars as pl


def map_to_truth(addr_map: pl.DataFrame, truth_addresses: pl.DataFrame,
                 truth_entities: pl.DataFrame,
                 min_purity: float = 0.6) -> tuple[pl.DataFrame, dict]:
    """resolved entity_id -> (true eid, illicit, typology, purity)."""
    j = addr_map.join(truth_addresses, on="address", how="inner")
    if j.height == 0:
        return pl.DataFrame({"entity": [], "true_eid": [], "illicit": [],
                             "typology": [], "purity": []}), {"matched_addresses": 0}

    counts = j.group_by(["entity_id", "eid"]).len()
    totals = counts.group_by("entity_id").agg(pl.col("len").sum().alias("total"))
    best = (counts.sort("len", descending=True)
            .group_by("entity_id").agg([pl.col("eid").first().alias("true_eid"),
                                        pl.col("len").first().alias("best_n")])
            .join(totals, on="entity_id", how="left"))
    best = best.with_columns((pl.col("best_n") / pl.col("total")).alias("purity"))

    labelled = (best.join(truth_entities.select(["eid", "illicit", "typology", "archetype"]),
                          left_on="true_eid", right_on="eid", how="left")
                .rename({"entity_id": "entity"}))
    labelled = labelled.with_columns([
        pl.col("illicit").fill_null(0).cast(pl.Int8),
        pl.col("typology").fill_null(""),
        pl.col("archetype").fill_null("unknown"),
    ])

    stats = {
        "matched_addresses": j.height,
        "labelled_entities": labelled.height,
        "illicit_entities": int(labelled.get_column("illicit").sum()),
        "mean_purity": round(float(labelled.get_column("purity").mean() or 0), 4),
        "impure_clusters": int(labelled.filter(pl.col("purity") < min_purity).height),
    }
    return labelled.select(["entity", "true_eid", "illicit", "typology",
                            "archetype", "purity"]), stats
