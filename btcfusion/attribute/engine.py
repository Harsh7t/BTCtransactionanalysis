"""The attribution engine: given an on-chain entity, which network identity is
behind it, and how sure are we?

This runs the PS's actual verb. Every commercial product in this space treats
src_ip as a feature column; none of them run inference in this direction, because
none of them have a vantage point on the P2P network to run it from.

PIPELINE (roadmap §5.1):
  1. entity x IP co-occurrence matrix
  2. propagation-tree roots, per transaction            <- diffusion.py
  3. hypergeometric significance against a null model   <- significance.py
  4. infrastructure classification and penalty          <- infra.py
  5. behavioural timezone inference                     <- behaviour.py
  6. confidence, interval, and counterfactuals          <- confidence.py

DEGRADATION IS A FEATURE. Where the network layer is absent, or every candidate
address is a Tor exit, this returns nothing and says why. An attribution engine
that always produces an answer is not an attribution engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from ..graph.build import entity_ip_matrix
from . import behaviour as bh
from . import confidence as cf
from .diffusion import repeat_weight, root_evidence
from .infra import classify
from .significance import benjamini_hochberg, cooccurrence_significance


@dataclass
class Attribution:
    entity: str
    candidates: list[dict] = field(default_factory=list)
    behaviour: dict | None = None
    status: str = "ok"          # ok | no_network_layer | no_significant_link | suppressed
    note: str = ""


def attribute(df: pl.DataFrame, txs: pl.DataFrame, addr_map: pl.DataFrame,
              entities: list[str], *, alpha: float = 0.01,
              min_count: int = 2, top_k: int = 5) -> tuple[dict[str, Attribution], dict]:
    """Attribute a set of entities. Returns (entity -> Attribution, run stats)."""
    stats: dict = {"n_entities": len(entities)}

    m, ips, meta = entity_ip_matrix(df, addr_map, txs, entities)
    if not meta.get("available"):
        return ({e: Attribution(e, status="no_network_layer",
                                note="Capture contains no usable src_ip column; "
                                     "attribution is disabled and chain-side "
                                     "detection is unaffected.")
                 for e in entities},
                {**stats, "available": False})

    rows, cols, pvals, ppmi = cooccurrence_significance(m, min_count=min_count)
    stats.update({"n_pairs_tested": int(len(rows)), "n_ips": len(ips)})
    if len(rows) == 0:
        return ({e: Attribution(e, status="no_significant_link",
                                note="No entity-IP pair met the minimum observation count.")
                 for e in entities}, {**stats, "available": True})

    significant = benjamini_hochberg(pvals, alpha=alpha)
    stats["n_pairs_significant"] = int(significant.sum())
    stats["fdr_alpha"] = alpha

    # Infrastructure profile per IP, and behavioural profile per entity.
    infra = classify(df, txs)
    infra_by_ip = {r["ip"]: r for r in infra.iter_rows(named=True)}
    behaviour = bh.profile_entities(txs, entities)

    # Propagation-tree root evidence, keyed (entity, ip).
    roots = root_evidence(df, txs, entities)
    root_by_pair = {(r["entity"], r["ip"]): r for r in roots.iter_rows(named=True)}
    stats["n_root_pairs"] = roots.height

    counts = np.asarray(m[rows, cols]).ravel()
    out: dict[str, Attribution] = {}
    by_entity: dict[int, list[int]] = {}
    for k in np.where(significant)[0]:
        by_entity.setdefault(int(rows[k]), []).append(int(k))

    suppressed = 0
    for ei, entity in enumerate(entities):
        idxs = by_entity.get(ei, [])
        beh = behaviour.get(entity)
        if not idxs:
            out[entity] = Attribution(entity, behaviour=beh, status="no_significant_link",
                                      note="No entity-IP association survived FDR control; "
                                           "the observed co-occurrences are consistent with "
                                           "chance given each address's traffic volume.")
            continue

        cands: list[dict] = []
        for k in idxs:
            ip = ips[cols[k]]
            info = infra_by_ip.get(ip, {"asn_type": "unknown", "n_entities": 1})
            n_obs = int(counts[k])
            base = cf.significance_strength(float(pvals[k]), float(ppmi[k]))
            rw = float(repeat_weight(np.array([n_obs]))[0])

            r = root_by_pair.get((entity, ip))
            root_frac = float(min(1.0, (r["root_weight"] if r else 0.0) / max(n_obs, 1)))

            geo_tz = int(info.get("tz_offset_min", 0) or 0)
            tz_agree = 0.5
            if beh and beh.get("diurnality", 0) > 0.25:
                tz_agree = bh.agreement(beh["inferred_offset_min"], geo_tz)

            penalty = float(info.get("penalty", 0.6) or 0.6)
            conf = cf.compute_confidence(base, n_obs, root_frac, penalty, tz_agree, rw)
            half = cf.interval(conf, n_obs)

            cands.append({
                "ip": ip,
                "asn": int(info.get("asn", 0) or 0),
                "asn_org": info.get("asn_org", "unknown"),
                "asn_type": info.get("asn_type", "unknown"),
                "country": info.get("country", "ZZ"),
                "n_observations": n_obs,
                "n_entities_on_ip": int(info.get("n_entities", 1) or 1),
                "p_value": float(pvals[k]),
                "ppmi": round(float(ppmi[k]), 3),
                "root_hits": int(r["root_hits"]) if r else 0,
                "root_fraction": round(root_frac, 3),
                "infra_penalty": round(penalty, 3),
                "timezone_agreement": round(tz_agree, 2),
                "confidence": round(conf, 3),
                "interval": round(half, 3),
                "summary": cf.describe(entity, ip, info, conf, half, beh),
                "what_would_change_it": cf.counterfactuals(
                    conf, base, n_obs, root_frac, penalty, tz_agree, rw,
                    str(info.get("asn_type", "unknown")),
                    int(info.get("n_entities", 1) or 1)),
            })

        cands.sort(key=lambda c: -c["confidence"])
        cands = cands[:top_k]
        status, note = "ok", ""
        if cands and cands[0]["confidence"] < 0.15:
            status = "suppressed"
            suppressed += 1
            note = ("Every candidate address is shared infrastructure; attribution is "
                    "suppressed rather than reported at a confidence that would mislead.")
        out[entity] = Attribution(entity, candidates=cands, behaviour=beh,
                                  status=status, note=note)

    stats["n_suppressed"] = suppressed
    stats["available"] = True
    return out, stats


def to_rows(attributions: dict[str, Attribution]) -> list[dict]:
    """Flatten for storage."""
    rows = []
    for eid, a in attributions.items():
        for rank, c in enumerate(a.candidates, start=1):
            rows.append({"entity": eid, "rank": rank, "status": a.status, **{
                k: v for k, v in c.items() if k != "what_would_change_it"}})
    return rows
