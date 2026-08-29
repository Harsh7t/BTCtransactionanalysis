"""Validate against Elliptic++ (Elmougy & Liu, KDD'23) - the ACTOR level.

WHY THIS EXISTS, given we already validate on Elliptic. Elliptic is
transaction-level with 166 anonymised features. This system is ENTITY-level: it
resolves addresses into actors, describes each actor with 132 features, and
scores the actor. Validating a transaction classifier therefore validates
something we do not ship.

Elliptic++ adds 822,942 labelled WALLET ADDRESSES with 56 named, human-readable
features - lifetime in blocks, transaction counts, BTC sent/received, fees, gaps
between transactions, counterparty counts. Those are the same quantities our own
entity features compute, at the same unit of analysis. It is the closest thing to
a real-data test of what we actually built.

Two tracks here:

  A. wallet classification - our detector on real address-level labels.
  B. co-spend clustering  - our common-input-ownership heuristic (graph/resolve.py
     H1) run on the real AddrTx edge list, scored by whether addresses it groups
     together actually share a label.

Track B is the one that has never been possible before. Every clustering number
elsewhere in this project is measured against a generator that was told what the
right answer was.

WHAT NEITHER TRACK VALIDATES: Elliptic++ has no IP, port, or propagation data.
Its four graphs (addr-addr, addr-tx, tx-addr, tx-tx) are all chain-side. The
network-chain correlation this project is built around remains validated on
synthetic data only. No public dataset closes that gap - it needs a real
multi-vantage-point listener deployment.

Files are not committed (licence unstated upstream, 1.3 GB); every path degrades
to `available: False` rather than scoring nothing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

WALLETS = "wallets_features_classes_combined.csv"
ADDR_TX = "AddrTx_edgelist.csv"

CITATION = {
    "source": "Elmougy & Liu 2023, Elliptic++: A Graph Network of Bitcoin "
              "Transactions and Wallet Addresses (KDD '23)",
    # Repo URL lives in docs/external_validation.md, not here: `make offline-check`
    # greps application code for URLs and a citation string is indistinguishable
    # from an endpoint to a grep. A check with exceptions stops being a guarantee.
    "repo": "git-disl/EllipticPlusPlus on GitHub - see docs/external_validation.md",
    "licence": "not stated upstream - cite, do not redistribute",
}

# Elliptic++ wallet labels. NOTE the encoding differs from the transaction files,
# which use the STRING 'unknown'. Here unknown is the integer 3. Reusing the
# transaction loader's filter would work by accident, not by intent.
ILLICIT, LICIT, UNKNOWN = 1, 2, 3


def _has(root: Path, *names: str) -> bool:
    return all((root / n).exists() for n in names)


# --------------------------------------------------------------- track A
def load_wallets(root: Path) -> pl.DataFrame:
    """Labelled wallet rows only. One address may appear in several time steps."""
    df = pl.read_csv(root / WALLETS)
    df = df.filter(pl.col("class") != UNKNOWN)
    return df.with_columns((pl.col("class") == ILLICIT).cast(pl.Int8).alias("y"))


def validate_wallets(root: Path, seed: int = 20260826) -> dict:
    """Address-level classification under a temporal, address-DISJOINT split.

    Two traps live in this dataset and both inflate the score if ignored.

    (1) 1,268,260 rows cover 822,942 addresses: an address appears once per time
        step it was active in, and illicit addresses repeat ~2x on average. A
        plain temporal split puts the SAME address in train and test with the
        same label, so the model can memorise an identity rather than learn a
        behaviour. We drop test addresses that appear in train, and report the
        naive figure alongside so the size of the trap is visible rather than
        merely avoided.

    (2) Addresses with more rows would otherwise carry more weight in the test
        metric. The test set is reduced to one row per address.
    """
    from ..detect.supervised import SupervisedDetector
    from . import metrics as M

    df = load_wallets(root)
    step = pl.col("Time step")
    cut = int(np.quantile(df.get_column("Time step").unique().to_numpy(), 0.7))

    tr = df.filter(step < cut)
    te_all = df.filter(step >= cut)
    # one row per address in test: its earliest appearance in the test window
    te_all = te_all.sort(["address", "Time step"]).unique(subset=["address"], keep="first")

    seen = set(tr.get_column("address").unique().to_list())
    te = te_all.filter(~pl.col("address").is_in(list(seen)))

    drop = ["address", "class", "y"]
    names = [c for c in df.columns if c not in drop]
    Xtr = tr.select(names).to_numpy().astype(np.float32)
    ytr = tr.get_column("y").to_numpy()

    def score(frame: pl.DataFrame, model) -> dict:
        X = frame.select(names).to_numpy().astype(np.float32)
        y = frame.get_column("y").to_numpy()
        s = model.predict_proba(X)
        c = M.classification_report_at(y, s, 0.5)
        return {"n": int(len(y)), "positive_rate": round(float(y.mean()), 4),
                "pr_auc": M.evaluate(y, s, 0.5)["pr_auc"], "precision": c["precision"],
                "recall": c["recall"], "f1": c["f1"], "mcc": c["mcc"]}

    model = SupervisedDetector(seed=seed).fit(Xtr, ytr, names, n_estimators=300)
    headline = score(te, model)
    naive = score(te_all, model)

    return {
        "n_labelled_rows": int(df.height),
        "n_labelled_addresses": int(df.get_column("address").n_unique()),
        "train_steps": [int(tr.get_column("Time step").min()),
                        int(tr.get_column("Time step").max())],
        "test_steps": [int(te.get_column("Time step").min()),
                       int(te.get_column("Time step").max())],
        "n_train_rows": int(tr.height),
        "n_features": len(names),
        "headline_address_disjoint": headline,
        "naive_repeated_addresses": naive,
        "n_test_addresses_dropped_as_seen_in_train": int(te_all.height - te.height),
        "note": ("`headline_address_disjoint` is the figure to quote. "
                 "`naive_repeated_addresses` keeps addresses the model already saw "
                 "in training and is reported ONLY to show how much that inflates "
                 "the result."),
    }


# --------------------------------------------------------------- track B
def validate_cospend_clustering(root: Path, seed: int = 20260826) -> dict:
    """Run graph/resolve.py's H1 on real Bitcoin co-spends and score the clusters.

    There is no ground-truth actor mapping in Elliptic++, so purity cannot be
    measured directly. What CAN be measured is label agreement: if
    common-input-ownership really groups addresses belonging to one actor, then
    two addresses in the same cluster should carry the same illicit/licit label
    far more often than two addresses drawn at random.

    The control is a label shuffle over the same clusters, which holds the cluster
    size distribution fixed and destroys only the address-to-label assignment.
    Without it, a high agreement rate would say nothing - 95% of labelled
    addresses are licit, so almost any pairing agrees most of the time.

    ONLY H1 IS EXERCISED. The change-address heuristic (H2) needs per-transaction
    timestamps to decide which output is freshly minted, and Elliptic++ resolves
    time only to one of 49 coarse steps. Feeding it a 49-valued clock would
    manufacture change edges from tie-breaking rather than from evidence, so H2 is
    left inert here and stays validated on synthetic data alone.
    """
    from ..graph.resolve import resolve_entities

    edges = pl.read_csv(root / ADDR_TX)
    txs = (edges.group_by("txId").agg(pl.col("input_address").alias("input_addresses"))
           .rename({"txId": "txid"})
           .with_columns(
               pl.lit([], dtype=pl.List(pl.Utf8)).alias("output_addresses"),
               pl.lit(0).alias("timestamp"),
               pl.lit("p2pkh").alias("script_type")))

    mapping, stats = resolve_entities(txs)

    labels = (pl.read_csv(root / WALLETS, columns=["address", "class"])
              .unique(subset=["address"])
              .filter(pl.col("class") != UNKNOWN)
              .with_columns((pl.col("class") == ILLICIT).cast(pl.Int8).alias("y")))
    joined = mapping.join(labels.select(["address", "y"]), on="address", how="inner")

    def _groups(y: np.ndarray, ent: np.ndarray) -> list[np.ndarray]:
        order = np.argsort(ent, kind="stable")
        ent_s, y_s = ent[order], y[order]
        bounds = np.flatnonzero(ent_s[1:] != ent_s[:-1]) + 1
        return [g for g in np.split(y_s, bounds) if len(g) >= 2]

    def agreement(groups: list[np.ndarray], drop_largest: bool = False) -> dict:
        """Do same-cluster addresses share a label?

        Reported three ways on purpose. `micro` counts address PAIRS, which is the
        natural quantity but is dominated by the largest cluster - on real Bitcoin
        one exchange supercluster can hold most of the pairs in the dataset, and a
        pair-weighted number then describes that one cluster rather than the
        heuristic. `macro` gives every cluster equal weight. `micro_excl_largest`
        drops the biggest cluster entirely. Quote macro; show the others so the
        skew is visible instead of hidden.

        Counted combinatorially: a cluster of k addresses with p positives has
        C(p,2)+C(k-p,2) agreeing pairs out of C(k,2).
        """
        gs = sorted(groups, key=len)
        subsets = {"micro": gs, "micro_excl_largest": gs[:-1] if len(gs) > 1 else []}
        out: dict = {}
        for name, sub in subsets.items():
            agree = total = 0
            for g in sub:
                k, pos = len(g), int(g.sum())
                agree += pos * (pos - 1) // 2 + (k - pos) * (k - pos - 1) // 2
                total += k * (k - 1) // 2
            out[name] = round(agree / total, 4) if total else None
            if name == "micro":
                out["n_pairs"] = int(total)
        per = [(int(g.sum()) * (int(g.sum()) - 1) // 2
                + (len(g) - int(g.sum())) * (len(g) - int(g.sum()) - 1) // 2)
               / (len(g) * (len(g) - 1) // 2) for g in gs]
        out["macro"] = round(float(np.mean(per)), 4) if per else None
        return out

    y = joined.get_column("y").to_numpy()
    ent = joined.get_column("entity_id").to_numpy()
    groups = _groups(y, ent)
    observed = agreement(groups)

    # Control: shuffle labels across the same clusters. Holds the cluster size
    # distribution fixed and destroys only the address-to-label assignment, so any
    # remaining lift is attributable to the clustering rather than to the fact that
    # ~90% of labelled addresses are licit and almost any pairing agrees.
    rng = np.random.default_rng(seed)
    ctrl_runs = [agreement(_groups(rng.permutation(y), ent)) for _ in range(20)]
    control = {k: round(float(np.mean([c[k] for c in ctrl_runs])), 4)
               for k in ("micro", "macro", "micro_excl_largest")
               if ctrl_runs[0][k] is not None}

    sizes = np.array(sorted(len(g) for g in groups))
    all_sizes = np.array(sorted(
        joined.group_by("entity_id").len().get_column("len").to_list()))

    return {
        "heuristic": "H1 common-input-ownership only (see docstring for why not H2)",
        "n_transactions": int(txs.height),
        "n_addresses_clustered": stats["n_addresses"],
        "n_entities": stats["n_entities"],
        "cospend_edges": stats["cospend_edges"],
        "mean_addresses_per_entity": round(stats["mean_addresses_per_entity"], 3),
        "n_labelled_addresses_in_clusters": int(joined.height),
        "cluster_sizes_labelled": {
            "n_multi_address_clusters": int(len(sizes)),
            "max": int(all_sizes.max()) if len(all_sizes) else 0,
            "p50": int(np.percentile(all_sizes, 50)) if len(all_sizes) else 0,
            "p99": int(np.percentile(all_sizes, 99)) if len(all_sizes) else 0,
        },
        "largest_entity_addresses_all": stats["largest_entity_addresses"],
        "label_agreement": observed,
        "label_agreement_shuffled_control": control,
        "lift_macro": (round(observed["macro"] / control["macro"], 3)
                       if control.get("macro") else None),
        "lift_micro_excl_largest": (
            round(observed["micro_excl_largest"] / control["micro_excl_largest"], 3)
            if control.get("micro_excl_largest") else None),
        "note": ("Quote `macro` - every cluster weighted equally. `micro` is "
                 "pair-weighted and therefore dominated by the largest cluster, which "
                 "is why the size distribution is reported next to it. The control "
                 "shuffles labels across the SAME clusters, holding sizes fixed."),
    }


# --------------------------------------------------------------- entry point
def validate_elliptic_pp(root: Path, seed: int = 20260826) -> dict:
    root = Path(root)
    out: dict = {"citation": CITATION}
    if not _has(root, WALLETS):
        return {**out, "available": False, "note": (
            f"Elliptic++ not present. Download {WALLETS} and {ADDR_TX} from "
            f"the Elliptic++ repo ({CITATION['repo']}) into {root}/ and re-run "
            "`make validate-elliptic-pp`. "
            "Not committed: 1.3 GB and no upstream licence.")}

    out["available"] = True
    out["wallet_classification"] = validate_wallets(root, seed)
    out["cospend_clustering"] = (
        validate_cospend_clustering(root, seed) if _has(root, ADDR_TX)
        else {"available": False, "note": f"{ADDR_TX} absent"})
    out["scope"] = ("Chain-side and actor-level only. Elliptic++ has no IP, port or "
                    "propagation data, so it cannot exercise the network-chain "
                    "correlation this project is built around.")
    return out
