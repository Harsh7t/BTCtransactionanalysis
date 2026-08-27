"""Per-entity feature extraction: where domain knowledge enters the model.

Six families. Every feature carries a one-line statement of the real-world
behaviour it is meant to capture - the roadmap's rule is that if you cannot write
that sentence, the feature should be deleted (§6.5).

Two families exist specifically because the PS names fields that naive designs
ingest and then never analyse:
  * PORT-DERIVED (§16.2-A) - src_port/dst_port. Ephemeral port ranges differ by
    OS, and a src_port of 8333 means an inbound-listening node rather than a leaf
    client. Nearly free signal about the announcing host.
  * SCRIPT-TYPE DERIVED (§16.2-B) - script_type. Uniform output scripts are one of
    the strongest CoinJoin signals available.

Everything is a whole-column Polars expression. Per-row Python over 170k
transactions costs minutes and would blow the §5.2 budget on its own.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ..graph.resolve import script_of_address

ROUND_SATS = 100_000_000          # 1 BTC
STRUCTURING_BAND = (0.80, 0.999)  # "just under a round threshold"


def _entropy_of_list(col: str) -> pl.Expr:
    """Shannon entropy of a list of amounts, normalised to [0,1].

    Near zero means every output is the same size - the CoinJoin / mixer
    signature. Near one means a natural spread of payment sizes.
    """
    total = pl.col(col).list.sum()
    p = pl.col(col).list.eval(pl.element() / pl.element().sum().clip(1))
    h = p.list.eval(-(pl.element() * (pl.element().clip(1e-12)).log())).list.sum()
    n = pl.col(col).list.len().clip(2)
    return pl.when(total > 0).then(h / n.log()).otherwise(0.0)


def transaction_features(txs: pl.DataFrame) -> pl.DataFrame:
    """Per-transaction derived columns, consumed by the entity aggregation below
    and re-used directly by the transaction-level alert head (§16.4-G)."""
    t = txs.with_columns([
        pl.col("output_amounts").list.sum().alias("value_out"),
        pl.col("output_amounts").list.len().alias("n_outputs"),
        pl.col("input_addresses").list.len().alias("n_inputs"),
        _entropy_of_list("output_amounts").alias("output_entropy"),
        pl.col("output_amounts").list.min().alias("min_out"),
        pl.col("output_amounts").list.max().alias("max_out"),
    ])
    t = t.with_columns([
        # A peel chain's tell: one tiny output beside one large remainder.
        pl.when(pl.col("n_outputs") == 2)
          .then(pl.col("min_out") / pl.col("value_out").clip(1))
          .otherwise(None).alias("peel_ratio"),
        (pl.col("fee") / pl.col("value_out").clip(1)).alias("fee_ratio"),
        # Fee RATE, sat/vbyte. By construction this is a function of the network
        # congestion at the transaction's timestamp and nothing else, which makes
        # it the pure probe for whether fees leak (raw fee scales with tx size,
        # so it legitimately carries structural signal).
        (pl.col("fee") / (11 + 68 * pl.col("n_inputs") + 31 * pl.col("n_outputs")).clip(1))
        .alias("feerate_sat_vb"),
        # Round-number payments are human-chosen amounts, not market-priced ones.
        (pl.col("output_amounts").list.eval(
            (pl.element() % 1_000_000 == 0).cast(pl.Int8)).list.mean()).alias("round_frac"),
        # Structuring: value parked deliberately just below a reporting threshold.
        (pl.col("output_amounts").list.eval(
            ((pl.element() % ROUND_SATS) > int(STRUCTURING_BAND[0] * ROUND_SATS)).cast(pl.Int8)
        ).list.mean()).alias("structuring_frac"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("timestamp").dt.weekday().alias("weekday"),
    ])
    return t


def _script_features(txs: pl.DataFrame) -> pl.DataFrame:
    """Wallet-software fingerprinting from output address encodings."""
    ex = (txs.select(["txid", "sender_entity", "output_addresses", "script_type"])
          .drop_nulls("sender_entity")
          .explode("output_addresses")
          .rename({"output_addresses": "address"})
          .drop_nulls("address")
          .with_columns(script_of_address(pl.col("address")).alias("out_script")))
    return (ex.group_by("sender_entity").agg([
        pl.col("out_script").n_unique().alias("script_diversity"),
        # Uniform output scripts across everything an entity ever paid is a
        # strong CoinJoin/mixer indicator.
        (pl.col("out_script").mode().first().is_not_null().cast(pl.Float32)
         * (pl.col("out_script") == pl.col("out_script").mode().first())
         .mean()).alias("script_uniformity"),
        (pl.col("out_script") == "p2tr").mean().alias("taproot_frac"),
        pl.col("out_script").is_in(["p2wpkh", "p2wsh", "p2tr"]).mean().alias("segwit_frac"),
        # How often change matched the spending wallet's own script type.
        (pl.col("out_script") == pl.col("script_type")).mean().alias("change_script_match_rate"),
    ]).rename({"sender_entity": "entity"}))


def _temporal_features(t: pl.DataFrame) -> pl.DataFrame:
    """Activity rhythm. Burstiness and dormancy are what separate a rapid-layering
    chain from a peel chain that happens to have the same shape."""
    s = (t.drop_nulls("sender_entity").sort("timestamp")
         .group_by("sender_entity")
         .agg([
             pl.col("timestamp").min().alias("first_ts"),
             pl.col("timestamp").max().alias("last_ts"),
             pl.len().alias("n_tx_sent"),
             pl.col("timestamp").diff().dt.total_seconds().mean().alias("gap_mean"),
             pl.col("timestamp").diff().dt.total_seconds().std().alias("gap_std"),
             pl.col("timestamp").diff().dt.total_seconds().max().alias("gap_max"),
             pl.col("hour_utc").alias("_hours"),
             (pl.col("weekday") >= 6).mean().alias("weekend_ratio"),
         ]))
    # Hour-of-day entropy: a 24/7 exchange scores near 1, a human in one timezone
    # scores well below it.
    hours = s.get_column("_hours").to_list()
    ent = np.zeros(len(hours), dtype=np.float32)
    for i, hs in enumerate(hours):
        if not hs:
            continue
        c = np.bincount(np.asarray(hs, dtype=np.int64), minlength=24).astype(float)
        p = c / c.sum()
        nz = p[p > 0]
        ent[i] = float(-(nz * np.log(nz)).sum() / np.log(24))
    s = s.drop("_hours").with_columns(pl.Series("hour_entropy", ent))

    return s.with_columns([
        ((pl.col("last_ts") - pl.col("first_ts")).dt.total_seconds() / 86400.0)
        .alias("lifespan_days"),
        # Burstiness coefficient (Goh & Barabasi): +1 = perfectly bursty,
        # -1 = perfectly regular, 0 = Poisson.
        ((pl.col("gap_std") - pl.col("gap_mean"))
         / (pl.col("gap_std") + pl.col("gap_mean")).clip(1)).alias("burstiness"),
        (pl.col("gap_max")
         / (pl.col("last_ts") - pl.col("first_ts")).dt.total_seconds().clip(1))
        .alias("dormancy_ratio"),
    ]).rename({"sender_entity": "entity"})


def _amount_features(t: pl.DataFrame) -> pl.DataFrame:
    return (t.drop_nulls("sender_entity").group_by("sender_entity").agg([
        pl.col("value_out").sum().alias("total_out"),
        pl.col("value_out").mean().alias("mean_value_out"),
        pl.col("value_out").std().alias("std_value_out"),
        pl.col("output_entropy").mean().alias("output_entropy_mean"),
        pl.col("output_entropy").min().alias("output_entropy_min"),
        pl.col("peel_ratio").mean().alias("peel_ratio_mean"),
        pl.col("peel_ratio").is_not_null().mean().alias("two_output_frac"),
        pl.col("fee_ratio").mean().alias("fee_ratio_mean"),
        # Raw fee in satoshis. Kept separate from fee_ratio because fee_ratio is
        # fee/value and therefore an AMOUNT feature in disguise; the honest test of
        # whether fees leak has to use the fee itself.
        pl.col("fee").mean().alias("mean_fee_sat"),
        pl.col("feerate_sat_vb").mean().alias("mean_feerate_sat_vb"),
        pl.col("round_frac").mean().alias("round_number_frac"),
        pl.col("structuring_frac").mean().alias("structuring_proximity"),
        pl.col("n_outputs").mean().alias("mean_n_outputs"),
        pl.col("n_outputs").max().alias("max_n_outputs"),
        pl.col("n_inputs").mean().alias("mean_n_inputs"),
        pl.col("n_inputs").max().alias("max_n_inputs"),
    ]).rename({"sender_entity": "entity"}))


def _network_features(df: pl.DataFrame, txs: pl.DataFrame) -> pl.DataFrame:
    """Announcement-side behaviour: who announced this entity's transactions, from
    where, on what infrastructure, and how consistently."""
    owner = txs.select(["txid", "sender_entity"]).drop_nulls("sender_entity")
    a = df.join(owner, on="txid", how="inner")
    if a.height == 0 or "src_ip" not in a.columns:
        return pl.DataFrame({"entity": []})

    aggs = [
        pl.col("src_ip").n_unique().alias("n_ips"),
        pl.len().alias("n_announcements"),
        pl.col("txid").n_unique().alias("n_tx_observed"),
    ]
    if "src_asn" in a.columns:
        aggs += [
            pl.col("src_asn").n_unique().alias("n_asns"),
            pl.col("src_country").n_unique().alias("n_countries"),
            pl.col("is_tor").mean().alias("tor_frac"),
            pl.col("is_vpn").mean().alias("vpn_frac"),
            pl.col("is_shared_infra").mean().alias("shared_infra_frac"),
            (pl.col("src_asn_type") == "residential").mean().alias("residential_frac"),
            (pl.col("src_asn_type") == "hosting").mean().alias("hosting_frac"),
            (pl.col("src_asn_type") == "mobile").mean().alias("mobile_frac"),
        ]
    if "src_port" in a.columns:
        aggs += [
            # A src_port of 8333 means an inbound-listening node: infrastructure,
            # not a leaf wallet.
            (pl.col("src_port") == 8333).mean().alias("listening_node_ratio"),
            # Ephemeral range fingerprints the announcing host's OS for free.
            ((pl.col("src_port") >= 32768) & (pl.col("src_port") <= 60999))
            .mean().alias("ephemeral_linux_frac"),
            (pl.col("src_port") >= 49152).mean().alias("ephemeral_windows_frac"),
            pl.col("src_port").n_unique().alias("n_src_ports"),
        ]
    if "dst_port" in a.columns:
        aggs.append((pl.col("dst_port") != 8333).mean().alias("nonstandard_dst_port_frac"))
    if "dst_ip" in a.columns:
        # Peer-topology: how widely this entity's traffic fanned out across the
        # network, from a field most designs ignore entirely (§16.2-C).
        aggs.append(pl.col("dst_ip").n_unique().alias("n_peers_reached"))

    out = a.group_by("sender_entity").agg(aggs).rename({"sender_entity": "entity"})
    return out.with_columns([
        (pl.col("n_announcements") / pl.col("n_tx_observed").clip(1))
        .alias("announcements_per_tx"),
        (pl.col("n_ips") / pl.col("n_tx_observed").clip(1)).alias("ip_churn_rate"),
    ])


def _counterparty_features(edges: pl.DataFrame) -> pl.DataFrame:
    """Concentration of an entity's business.

    The Herfindahl index separates an exchange (thousands of counterparties, tiny
    concentration) from a laundering hop (one counterparty, HHI = 1).
    """
    tot = edges.group_by("src").agg(pl.col("value").sum().alias("_tot"))
    e = edges.join(tot, on="src", how="left")
    e = e.with_columns((pl.col("value") / pl.col("_tot").clip(1)).alias("share"))
    out_side = e.group_by("src").agg([
        pl.col("dst").n_unique().alias("n_counterparties_out"),
        (pl.col("share") ** 2).sum().alias("counterparty_hhi"),
    ]).rename({"src": "entity"})
    in_side = edges.group_by("dst").agg([
        pl.col("src").n_unique().alias("n_counterparties_in"),
        pl.col("value").sum().alias("total_in"),
    ]).rename({"dst": "entity"})
    return out_side.join(in_side, on="entity", how="full", coalesce=True)


def build_feature_matrix(df: pl.DataFrame, txs: pl.DataFrame, edges: pl.DataFrame,
                         graph, nodes: list[str],
                         cluster_sizes: pl.DataFrame | None = None) -> pl.DataFrame:
    """Join every family into one entity-indexed matrix."""
    t = transaction_features(txs)
    base = pl.DataFrame({"entity": nodes})

    parts = [
        _temporal_features(t), _amount_features(t), _script_features(txs),
        _network_features(df, txs), _counterparty_features(edges),
    ]
    for p in parts:
        if p.height:
            base = base.join(p, on="entity", how="left")

    topo = graph.topology()
    # Reach ratios distinguish a long thin peel chain from a wide shallow fan-out
    # far more cheaply than computing longest paths.
    g = graph.g
    r1 = np.asarray(g.neighborhood_size(order=1, mode="out"), dtype=np.float32)
    r3 = np.asarray(g.neighborhood_size(order=3, mode="out"), dtype=np.float32)
    topo["reach_1"] = r1
    topo["reach_3"] = r3
    topo["chain_linearity"] = r3 / np.clip(r1, 1, None)
    topo_df = pl.DataFrame({"entity": graph.nodes, **{k: v for k, v in topo.items()}})
    base = base.join(topo_df, on="entity", how="left")

    if cluster_sizes is not None and cluster_sizes.height:
        base = base.join(cluster_sizes, on="entity", how="left")

    base = base.with_columns([
        (pl.col("total_out").fill_null(0) / pl.col("total_in").fill_null(0).clip(1))
        .alias("in_out_ratio"),
    ])
    num = [c for c, dt in base.schema.items()
           if c != "entity" and dt.is_numeric()]
    base = base.with_columns([pl.col(c).cast(pl.Float32).fill_null(0.0).fill_nan(0.0)
                              for c in num])
    return base.select(["entity"] + sorted(num))


def feature_names(matrix: pl.DataFrame) -> list[str]:
    return [c for c in matrix.columns if c != "entity"]
