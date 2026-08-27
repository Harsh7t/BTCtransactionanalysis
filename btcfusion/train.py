"""Training: fit, calibrate, evaluate, and write every number to metrics.json.

Non-negotiables, all enforced rather than intended (roadmap §6.6):
  1. Group-aware splitting - one entity never straddles the boundary.
  2. Temporal ordering    - test is strictly later than train.
  3. Calibration on its own fold - never on the test set.
  4. Held-out typologies never appear in training. Not one example.
  5. Fixed seeds everywhere.
  6. Artefacts versioned and hashed, with a manifest.

metrics.json is the single source for every figure that appears in the write-up
or on a slide. If a number is not in this file, it is not a result.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import polars as pl

from .detect.fuse import Calibrator, fuse_scores
from .detect.novelty import NoveltyDetector
from .detect.supervised import SupervisedDetector
from .detect.typologies import evidence_strength
from .eval import metrics as M
from .eval.labels import map_to_truth
from .eval.splits import make_splits, split_report
from .pipeline import load_cfg, prepare, provenance


def train(capture: Path, truth_dir: Path, artifacts: Path,
          db: Path | None = None) -> dict:
    cfg = load_cfg("detect.yaml")
    seed = int(cfg["seed"])
    artifacts = Path(artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    prep = prepare(Path(capture), detect_cfg=cfg)

    truth_dir = Path(truth_dir)
    truth_addr = pl.read_csv(truth_dir / "truth_addresses.csv")
    truth_ent = pl.read_csv(truth_dir / "truth_entities.csv")
    labels, label_stats = map_to_truth(prep.addr_map, truth_addr, truth_ent)

    fm = prep.fm
    # An entity's first appearance is the earliest transaction it took part in on
    # EITHER side. Using only the send side leaves every receive-only entity with
    # a null timestamp; filling those to the maximum then sweeps all of them into
    # the final temporal split, which is how the test fold ended up 0.6% illicit
    # while training was 12.8%. A temporal split has to order entities by when
    # they actually appeared, not by when they happened to spend.
    sent_ts = (prep.txs.select(["sender_entity", "timestamp"])
               .rename({"sender_entity": "entity"}).drop_nulls("entity"))
    recv_ts = (prep.txs.select(["receiver_entities", "timestamp"])
               .explode("receiver_entities")
               .rename({"receiver_entities": "entity"}).drop_nulls("entity"))
    first_ts = (pl.concat([sent_ts, recv_ts])
                .group_by("entity").agg(pl.col("timestamp").min().alias("first_ts")))

    splits = make_splits(fm, labels, first_ts,
                         cfg["splits"]["holdout_typologies"],
                         fracs=(cfg["splits"]["train"], cfg["splits"]["calib"],
                                cfg["splits"]["test"]),
                         seed=seed)

    lab = dict(zip(labels.get_column("entity").to_list(),
                   labels.get_column("illicit").to_list()))
    y = np.array([lab.get(e, 0) for e in prep.nodes], dtype=np.int8)
    X = prep.X

    tr, ca, te, ho = splits["train"], splits["calib"], splits["test"], splits["holdout_typology"]

    # ---- fit -------------------------------------------------------------
    sup = SupervisedDetector(seed=seed, backend=cfg["supervised"]["backend"]) \
        .fit(X[tr], y[tr], prep.feature_names,
             n_estimators=int(cfg["supervised"]["n_estimators"]))
    nov = NoveltyDetector(seed=seed,
                          contamination=float(cfg["novelty"]["contamination"])).fit(X[tr])
    cluster_labels = nov.cluster(X, min_cluster_size=int(cfg["novelty"]["min_cluster_size"]))

    ev_df = evidence_strength(fm, prep.txs, prep.nodes)
    ev_map = dict(zip(ev_df.get_column("entity").to_list(),
                      ev_df.get_column("evidence_strength").to_list()))
    ev = np.array([ev_map.get(e, 0.0) for e in prep.nodes], dtype=np.float32)

    def raw_scores(idx):
        return fuse_scores(sup.predict_proba(X[idx]), nov.score(X[idx]), ev[idx],
                           cfg["fusion"]["weights"])

    # ---- calibrate on its OWN fold ---------------------------------------
    cal = Calibrator().fit(raw_scores(ca), y[ca])

    # ---- evaluate ---------------------------------------------------------
    threshold = float(cfg["alerts"]["threshold"])
    results: dict = {}
    for name, idx in (("train", tr), ("calib", ca), ("test", te)):
        r_raw = raw_scores(idx)
        r_cal = cal.transform(r_raw, adjust_prior=True)
        results[name] = M.evaluate(y[idx], r_cal, threshold)
        results[name]["ece_uncalibrated"] = round(
            M.expected_calibration_error(y[idx], r_raw), 4)
        results[name]["ece_no_prior_correction"] = round(
            M.expected_calibration_error(y[idx], cal.transform(r_raw)), 4)
        results[name]["calibration_fold_prior"] = round(cal.calib_prior, 4)
        results[name]["estimated_prior"] = round(cal.last_estimated_prior, 4)

    if len(ho):
        # The held-out set is 100% positive by construction, so PR-AUC on it alone
        # is undefined. Score it against the test fold's negatives instead: that
        # asks the question we actually care about - can the model pull a
        # laundering pattern it has never seen out of a realistic haystack?
        neg = te[y[te] == 0]
        mixed = np.concatenate([ho, neg])
        mixed_scores = cal.transform(raw_scores(mixed), adjust_prior=True)
        ho_cal = cal.transform(raw_scores(ho), adjust_prior=True)
        results["holdout_typology"] = {
            **M.evaluate(y[mixed], mixed_scores, threshold),
            "recall_at_threshold": round(M.held_out_recall(y[ho], ho_cal, threshold), 4),
            "n_holdout_positives": int(len(ho)),
            "n_negatives_mixed_in": int(len(neg)),
            "typologies": cfg["splits"]["holdout_typologies"],
            "note": ("Laundering patterns the model never trained on, scored against the "
                     "test fold's negatives. Expected to be materially worse than the test "
                     "score - that gap IS the finding, and it is the honest bound on "
                     "generalisation to unseen typologies."),
        }

    te_cal = cal.transform(raw_scores(te), adjust_prior=True)
    reliability = M.reliability_curve(y[te], te_cal)

    # ---- ablation: where does the lift actually come from? ---------------
    # The shipped configuration is passed in as the final row. Without it the
    # table ends on the pure supervised score while the scorecard reports the
    # FUSED, CALIBRATED one - two different numbers for "the model", which is
    # exactly the inconsistency a reviewer pounces on. Fusion trades a little
    # ranking quality for robustness on typologies the classifier never saw, and
    # the table should show that trade rather than stop one row early.
    ablation = _ablation(X, y, tr, te, prep.feature_names, cfg, seed, ev,
                         shipped=te_cal)

    # The fusion weights are a real trade-off between precision on KNOWN
    # typologies and recall on UNSEEN ones. Sweeping it here means the shipped
    # configuration is a measured choice on a published curve, not a preference.
    fusion_sweep = _fusion_sweep(sup, nov, ev, X, y, ca, te, ho, cfg, threshold)

    # ---- persist ----------------------------------------------------------
    sup.save(artifacts / "supervised.pkl")
    nov.save(artifacts / "novelty.pkl")
    cal.save(artifacts / "calibrator.pkl")
    (artifacts / "feature_names.json").write_text(json.dumps(prep.feature_names))

    metrics = {
        "results": results,
        "reliability_curve": reliability,
        "ablation": ablation,
        "fusion_sweep": fusion_sweep,
        "splits": split_report(labels, splits, fm),
        "label_mapping": label_stats,
        "entity_resolution": prep.resolve_stats,
        "behavioural_clusters": nov.cluster_stats_,
        "feature_importance": dict(sorted(sup.feature_importance(X[tr]).items(),
                                          key=lambda kv: -kv[1])[:25]),
        "embeddings": prep.embed_meta,
        "timings": prep.timings,
        "train_duration_s": round(time.perf_counter() - t0, 2),
    }
    manifest = {
        "version": artifacts.name,
        "backend": sup.backend,
        "seed": seed,
        "feature_version": cfg["feature_version"],
        "n_features": len(prep.feature_names),
        "n_train_rows": int(len(tr)),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provenance": provenance(Path(capture), cfg),
        "metrics": metrics,
    }
    (artifacts / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (artifacts / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def _ablation(X, y, tr, te, names, cfg, seed, ev, shipped=None) -> list[dict]:
    """Rules -> +unsupervised -> +GBDT -> +embeddings. The slide that shows the
    model is doing work the rules cannot."""
    n_eng = len([n for n in names if not n.startswith("emb_")])
    out = []

    out.append({"stage": "typology rules only",
                **_score(y[te], ev[te])})

    nov = NoveltyDetector(seed=seed).fit(X[tr][:, :n_eng])
    out.append({"stage": "+ unsupervised novelty",
                **_score(y[te], nov.score(X[te][:, :n_eng]))})

    s1 = SupervisedDetector(seed=seed, backend=cfg["supervised"]["backend"]).fit(
        X[tr][:, :n_eng], y[tr], names[:n_eng], n_estimators=200)
    out.append({"stage": "+ GBDT on engineered features",
                **_score(y[te], s1.predict_proba(X[te][:, :n_eng]))})

    s2 = SupervisedDetector(seed=seed, backend=cfg["supervised"]["backend"]).fit(
        X[tr], y[tr], names, n_estimators=200)
    out.append({"stage": "+ Node2Vec embeddings",
                **_score(y[te], s2.predict_proba(X[te]))})

    if shipped is not None:
        out.append({"stage": "+ fusion & calibration (shipped)",
                    **_score(y[te], shipped),
                    "note": ("Fusion blends in unsupervised novelty and typology evidence. "
                             "It costs some ranking quality on KNOWN typologies and buys "
                             "coverage of unknown ones - see held-out recall.")})
    return out


def _fusion_sweep(sup, nov, ev, X, y, ca, te, ho, cfg, threshold) -> list[dict]:
    """Precision-vs-novelty trade-off across fusion weightings.

    Publishing this is the point. Any team can pick weights; being able to show
    the curve they sit on, and say which end of it the deployment context wants,
    is the difference between a tuned number and an engineering decision.
    """
    import numpy as np
    P, N = sup.predict_proba(X), nov.score(X)
    neg = te[y[te] == 0]
    mixed = np.concatenate([ho, neg]) if len(ho) else te
    grid = [(1.0, 0.0, 0.0), (0.90, 0.0, 0.10), (0.85, 0.05, 0.10),
            (0.80, 0.15, 0.05), (0.75, 0.15, 0.10), (0.65, 0.25, 0.10)]
    shipped = cfg["fusion"]["weights"]
    out = []
    for w_s, w_n, w_e in grid:
        W = {"supervised": w_s, "novelty": w_n, "evidence": w_e}
        fu = lambda i: fuse_scores(P[i], N[i], ev[i], W)   # noqa: E731
        cal = Calibrator().fit(fu(ca), y[ca])
        tc, mc = cal.transform(fu(te)), cal.transform(fu(mixed))
        hc = cal.transform(fu(ho)) if len(ho) else tc
        out.append({
            "supervised": w_s, "novelty": w_n, "evidence": w_e,
            "test_pr_auc": round(M.pr_auc(y[te], tc), 4),
            "precision_at_10": round(M.precision_at_k(y[te], tc, 10), 4),
            "precision_at_50": round(M.precision_at_k(y[te], tc, 50), 4),
            "holdout_pr_auc": round(M.pr_auc(y[mixed], mc), 4),
            "holdout_recall": round(M.held_out_recall(y[ho], hc, threshold), 4) if len(ho) else None,
            "shipped": (abs(w_s - float(shipped["supervised"])) < 1e-6
                        and abs(w_n - float(shipped["novelty"])) < 1e-6),
        })
    return out


def _score(y, s) -> dict:
    return {"pr_auc": round(M.pr_auc(y, s), 4),
            "precision_at_10": round(M.precision_at_k(y, s, 10), 4),
            "precision_at_50": round(M.precision_at_k(y, s, 50), 4)}
